import datetime
import logging
import queue
import re
import threading
import time
import warnings
from copy import deepcopy
from typing import cast, TYPE_CHECKING

import megahal
import twitter
from twitter.api import CHARACTER_LIMIT
from twitter.ratelimit import EndpointRateLimit

from twitterhal.conf import settings
from twitterhal.gracefulkiller import killer
from twitterhal.models import Tweet, TweetList
from twitterhal.runtime import runner
from twitterhal.twitter_api import TwitterApi


if TYPE_CHECKING:
    from typing import Union
    from .engine import DBInstance

logger = logging.getLogger(__name__)


class TwitterHAL:
    def __init__(
        self, screen_name=None, random_post_times=None, include_mentions=False,
        force=False, test=False
    ):
        """Initialize the bot.

        If not explicitly overridden here, arguments will be collected from
        `twitterhal.conf.settings`.

        Args:
            screen_name (str): Twitter screen name ("handle") for this bot
                (without the '@'!). Default: None
            random_post_times (list of datetime.time, optional): The times of
                day when random posts will be done. Defaults to 8:00, 16:00,
                and 22:00.
            include_mentions (bool, optional): Whether to include all
                @mentions in our replies, and not only that of the user we're
                replying to. Default: False
            force (bool, optional): Try and force actions even if TwitterHAL
                doesn't want to. Default: False
            test (bool, optional): Test mode; don't actually post anything.
                Default: False
        """
        # Take care of settings
        Database = settings.get_database_class()
        db_options = settings.DATABASE.get("options", {})
        if test:
            db_options.update(settings.DATABASE.get("test_options", {}))
        self.include_mentions = include_mentions or settings.INCLUDE_MENTIONS
        self.random_post_times = random_post_times or settings.RANDOM_POST_TIMES
        self.screen_name = screen_name or settings.SCREEN_NAME

        # Set up runtime stuff
        self.db = cast("DBInstance", Database(**db_options))
        self.force = force
        self.generate_random_lock = threading.Lock()
        self.megahal_open = False
        self.mention_queue = queue.Queue()
        self.post_queue = queue.Queue()
        self.test = test
        if self.test:
            logger.info("TEST MODE")

    """ ---------- METHODS FOR SETTING UP STUFF ---------- """

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *args, **kwargs):
        self.close()
        logger.debug("Exited gracefully =)")

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    def open(self):
        """
        Will *not* chicken out if Twitter authentication fails. But it will
        happen sooner or later.
        """
        logger.debug("Starting engine ...")
        self.init_db()
        logger.debug("Initializing Twitter API ...")
        self.api = TwitterApi(**self.get_twitter_api_kwargs())
        try:
            self.api.InitializeRateLimit()
        except (twitter.TwitterError, ConnectionError):
            pass
        self._init_post_status_limit()
        logger.debug("Ready!")

    def close(self):
        logger.debug("Closing DB ...")
        self.db.close()
        if self.megahal_open:
            logger.debug("Closing MegaHAL ...")
            self.megahal.close()
            self.megahal_open = False

    def prepare_runner(self):
        self._get_missing_own_tweets()
        self._get_missing_mentions()
        self._flag_replied_mentions()
        for mention in self.db.mentions.unanswered:
            self.mention_queue.put(mention)
        self.register_workers()
        self.register_loop_tasks()
        self.register_post_loop_tasks()

    def register_workers(self):
        runner.register_worker(self.post_tweets_worker)

    def register_loop_tasks(self):
        runner.register_loop_task(self.generate_random, sleep=60)
        runner.register_loop_task(self.get_new_mentions, sleep=15)
        runner.register_loop_task(self.pop_mention_and_generate_reply)

    def register_post_loop_tasks(self):
        pass

    def get_twitter_api_kwargs(self, **kwargs):
        defaults = deepcopy(settings.TWITTER_API)
        defaults.update(kwargs)
        logger.debug(defaults)
        return defaults

    def get_megahal_api_kwargs(self, **kwargs):
        defaults = deepcopy(settings.MEGAHAL_API)
        defaults.update(kwargs)
        logger.debug(defaults)
        return defaults

    def init_db(self):
        """Initialize TwitterHAL database

        If you extend the functionality and want to store additional values in
        the DB, this is the place to define them. Just do:

        >>> self.db.add_key(key_name, key_type, **default_kwargs)
        >>> super().init_db()
        """
        self.db.add_key("posted_tweets", TweetList, unique=True)
        self.db.add_key("mentions", TweetList, unique=True)
        logger.debug("Trying to initialize DB ...")
        self.db.open()
        logger.debug("DB initialized")

    @property
    def megahal(self):
        if not self.megahal_open:
            if megahal.VERSION >= (0, 4, 0):
                logger.info("Initializing MegaHAL, this could take a moment ...")
                Database = settings.get_megahal_database_class()
                db_options = settings.MEGAHAL_DATABASE.get("options", {})
                if self.test:
                    db_options.update(settings.MEGAHAL_DATABASE.get("test_options", {}))
                db = Database(**db_options)
                self._megahal = megahal.MegaHAL(db=db, **self.get_megahal_api_kwargs())
            else:
                self._megahal = megahal.MegaHAL(**self.get_megahal_api_kwargs())
            self.megahal_open = True
        return self._megahal

    """ ---------- SINGLETON WORKERS TO BE RUN CONTINUOUSLY ---------- """

    def post_tweets_worker(self, restart=False):
        """
        Worker that continuously fetches Tweet objects from self.post_queue
        and posts them.
        """
        if restart and self.generate_random_lock.locked():
            self.generate_random_lock.release()
        while not killer.kill_now or not self.post_queue.empty():
            if self.force or self.can_post():
                try:
                    tweet: "Tweet" = self.post_queue.get(timeout=3)
                except queue.Empty:
                    continue
                logger.debug(f"Got from post_queue: {tweet}")
                self._post_tweet(tweet)
            else:
                killer.sleep(5)
        logger.debug("Recevied exit event")

    """ ---------- LOOP TASKS ---------- """

    def generate_random(self):
        """Generate a random tweet and put it in post_queue

        Using Lock to prevent two random tweet being generated
        simultaneously. Lock is released by _post_tweet() after post
        has been attempted (whether it succeeded or not).
        """
        if not self.force and not self._time_for_random_post():
            logger.debug("Not yet time for random post")
            pass
        elif not self.generate_random_lock.acquire(blocking=False):
            logger.debug("Could not acquire lock")
        else:
            logger.info("Generating new random tweet ...")
            tweet = self.generate_tweet()
            logger.debug(f"Putting random tweet in post_queue: {tweet}")
            self.post_queue.put(tweet)

    def get_new_mentions(self):
        """Fetch new (unanswered) Tweets mentioning us

        Add new mentions to self.db.mentions, if they are not already in there.
        Also add them to mention_queue, to be picked up by
        pop_mention_and_generate_reply.

        TODO: Separate "new" from "unanswered" mentions?
        """
        if not self.force and not self.can_do_request("/statuses/mentions_timeline"):
            return TweetList()
        try:
            mentions = [
                Tweet.from_status(m) for m in self.api.GetMentions()
                if m not in self.db.mentions and
                m.user.screen_name.lower() not in [u.lower() for u in settings.BANNED_USERS]
            ]
        except (twitter.TwitterError, ConnectionError) as e:
            logger.error(str(e))
            return TweetList()
        else:
            self.db.mentions.extend(mentions)
            for mention in mentions:
                logger.info(f"Got new mention: {mention}")
                mention = self.process_new_mention(mention)
                self.mention_queue.put(mention)

    def pop_mention_and_generate_reply(self):
        """Get *one* Tweet from mention queue and generate a reply.

        Mentions in queue are *not* technically guaranteed to be unique, but
        at least they are if they were put there by self.get_new_mentions.
        Other implementations which may put things there will also have to
        ensure their uniqueness.

        Reply is put in post_queue for post_tweets_worker to pick up.

        TODO: Ej optimalt, går det att lösa bättre? Kanske med en ny
        bool-flagga på TweetList? Fast det vore nog inte threading-safe.
        Kanske ska TweetList ha en intern queue?
        """
        if self.force or self.can_post():
            try:
                mention = self.mention_queue.get_nowait()
            except queue.Empty:
                pass
            else:
                logger.debug(f"Generating reply to {mention}")
                reply = self.generate_tweet(in_reply_to=mention)
                logger.debug(f"Putting reply in post_queue: {reply}")
                self.post_queue.put(reply)

    """ ---------- PUBLIC METHODS USED BY WORKERS/TASKS ETC ---------- """

    def can_do_request(self, url, count=1):
        """Check if we can make request(s) to a given endpoint.

        Args:
            url (str): Twitter API endpoint, e.g. "/statuses/mentions_timeline"
            count (int, optional): For when we want to do several requests at
                one time. Default: 1

        Returns:
            True for success (we may do the request(s)), False otherwise
        """
        # It seems the API doesn't give numbers for POST /statuses/update or
        # POST /statuses/retweet/:id, so we keep track of those ourselves:
        if url == "/statuses/update" or url == "/statuses/retweet" or url.startswith("/statuses/retweet/"):
            return self.can_post()
        else:
            limit = self.api.CheckRateLimit(url)
            # Re-initialize rate limits if reset time has passed:
            if limit.reset and limit.reset <= time.time():
                self.api.InitializeRateLimit()
                limit = self.api.CheckRateLimit(url)
        logger.debug(f"limit.remaining: {limit.remaining}, count: {count}")
        return limit.remaining >= count

    def can_post(self, count=1):
        if self.post_status_limit.reset <= time.time():
            self._set_post_status_limit()
        logger.debug(f"self.post_status_limit.remaining: {self.post_status_limit.remaining}, count: {count}")
        return self.post_status_limit.remaining >= count

    def generate_tweet(self, in_reply_to=None, prefixes=[], suffixes=[]):
        """Generate a Tweet object

        Generate a new Tweet object from MegaHAL, with or without another Tweet
        to reply to. Does not post it or store it anywhere, just returns it.
        Used by self.generate_random() and self.generate_reply(). Does not set
        in_reply_to.is_answered; that will be done by self._post_tweet() once
        it actually has been posted.

        Args:
            in_reply_to (Tweet, optional): Another Tweet, to reply to. Will
                try to base content on that Tweet's text. Prefixes generated
                Tweet with handle of the sender and, optionally (if
                self.include_mentions == True), the handles of all other
                users mentioned.
            prefixes (list of str, optional): List of strings that will be put
                in the beginning of the generated Tweet, separated by space.
                (NB: If this is a reply, the handle(s) of the repliee(s) will
                be put in the very beginning, with these strings after)
            suffixes (list of str, optional): List of strings that will be put
                in the end of the generated Tweet, separated by space.
                Hashtags maybe?

        Returns:
            models.Tweet object
        """
        start_time = datetime.datetime.now().time().isoformat("seconds")
        if in_reply_to:
            mentions = ["@" + in_reply_to.user.screen_name]
            if self.include_mentions:
                mentions += [
                    # Negative lookbehind to avoid matching email addresses
                    handle for handle in re.findall(r"(?<!\w)@[a-z0-9_]+", in_reply_to.text, flags=re.IGNORECASE)
                    if handle.lower() not in [
                        "@" + self.screen_name,
                        "@" + in_reply_to.user.screen_name.lower(),
                        *["@" + user.lower() for user in settings.BANNED_USERS]
                    ]
                ]
            prefix = " ".join(mentions + prefixes) + " "
        elif prefixes:
            prefix = " ".join(prefixes) + " "
        else:
            prefix = ""
        if suffixes:
            suffix = " " + " ".join(suffixes)
        else:
            suffix = ""

        phrase = in_reply_to.filtered_text if in_reply_to else ""
        reply = self.megahal.get_reply(phrase, max_length=CHARACTER_LIMIT - len(prefix) - len(suffix))
        while (not reply or self.db.posted_tweets.fuzzy_duplicates(reply.text)) and not killer.kill_now:
            # If, for some reason, we got an empty or duplicate reply: keep
            # trying, but don't learn from the input again
            if not reply:
                logger.info(f"Got empty reply, trying again (since {start_time})")
            else:
                logger.info(f"Got duplicate reply, trying again (since {start_time}): {reply}")
            reply = self.megahal.get_reply_nolearn(phrase, max_length=CHARACTER_LIMIT - len(prefix) - len(suffix))
        text = prefix + reply.text + suffix
        tweet = Tweet(
            text=text, filtered_text=text,
            in_reply_to_status_id=in_reply_to.id if in_reply_to is not None else None
        )
        logger.debug(f"Generated: {tweet}")
        return tweet

    def process_new_mention(self, mention):
        """Hook for doing what you need to do when a new mention comes in"""
        return mention

    """ ---------- HELPFUL (?) UTILITY METHODS ---------- """

    def post_from_queue(self):
        """Post all queued Tweets

        Not used in the daemon loop, exists more like a little helper for
        those who may want it. Simply loops through the internal queue of
        Tweets and posts them.
        """
        while not self.post_queue.empty():
            if not self.force and not self.can_post():
                logger.info("Rate limit prohibits us from posting at this time")
                break
            tweet: "Tweet" = self.post_queue.get()
            logger.info(f"Got from post_queue: {tweet}")
            self._post_tweet(tweet)

    def post_random_tweet(self):
        """Post a new random Tweet

        Not used in the daemon loop. Just posts a new random Tweet on demand.
        """
        tweet = self.generate_tweet()
        if self.force or self.can_post():
            self._post_tweet(tweet)

    """ ---------- PRIVATE HELPER METHODS ---------- """

    def _flag_replied_mentions(self):
        # Make sure _get_missing_mentions() and _get_missing_own_tweets() is
        # run *before* this one
        logger.info("Flagging replied mentions ...")
        in_reply_to_ids = [t.in_reply_to_status_id for t in self.db.posted_tweets.replies]
        for mention in [t for t in self.db.mentions.unanswered if t.id in in_reply_to_ids]:
            mention.is_answered = True

    def _get_missing_mentions(self):
        logger.info("Fetching mentions ...")
        try:
            since_id = max([t.id for t in self.db.mentions])
        except ValueError:
            since_id = None
        tweets = self.api.GetMentions(since_id=since_id, count=200)
        self.db.mentions.extend([Tweet.from_status(t) for t in tweets])

    def _get_missing_own_tweets(self):
        logger.info("Fetching own posted tweets ...")
        try:
            since_id = max([t.id for t in self.db.posted_tweets])
        except ValueError:
            since_id = None
        tweets = self.api.GetUserTimeline(screen_name=self.screen_name, since_id=since_id, count=200)
        self.db.posted_tweets.extend([Tweet.from_status(t) for t in tweets])

    def _init_post_status_limit(self):
        """Initialize status/retweet post limit data

        Since Twitter API for some reason doesn't supply these numbers, we
        make an effort to keep track of them ourselves, going after the limits
        specified at:
        https://developer.twitter.com/en/docs/tweets/post-and-engage/api-reference/post-statuses-retweet-id
        """
        since = time.time() - 3 * 60 * 60
        try:
            latest_posts = self.api.GetUserTimeline(screen_name=self.screen_name, count=200, trim_user=True)
        except twitter.TwitterError:
            warnings.warn("Could not connect to Twitter API! Keys/secrets incorrect?")
        else:
            # Limit within the 3 hour window is 300 requests, but Twitter only lets
            # us fetch 200 at a time
            if latest_posts and len(latest_posts) > 190 and latest_posts[-1].created_at_in_seconds > since:
                latest_posts += self.api.GetUserTimeline(
                    screen_name=self.screen_name, count=200, since_id=latest_posts[-1].id, trim_user=True
                )
            latest_posts = [p for p in latest_posts if p.created_at_in_seconds > since]
            self._set_post_status_limit(subtract=len(latest_posts))

    def _post_tweet(self, tweet):
        # Checking can_post is the responsibility of the caller.
        try:
            if self.test:
                try:
                    last_id = self.db.posted_tweets[-1].id
                except IndexError:
                    last_id = 0
                status = twitter.Status(
                    id=last_id + 1,
                    full_text=tweet.text,
                    in_reply_to_status_id=tweet.in_reply_to_status_id
                )
            else:
                status = self.api.PostUpdate(
                    tweet.text, in_reply_to_status_id=tweet.in_reply_to_status_id)
        except (twitter.TwitterError, ConnectionError) as e:
            logger.error(f"Twitter raised error for {tweet}: {e}")
        else:
            # Logging the request here, since I guess it counts towards
            # the rate limit regardless of whether we succeed or not
            self._set_post_status_limit(subtract=1)
            tweet.extend(status)
            self.db.posted_tweets.append(tweet)
            if tweet.in_reply_to_status_id:
                # This was a reply to a mention
                original_tweet = self.db.mentions.get_by_id(tweet.in_reply_to_status_id)
                if original_tweet:
                    original_tweet.is_answered = True
                logger.info(f"Posted: {tweet} as reply to: {original_tweet}")
            else:
                logger.info(f"Posted: {tweet}")
        if not tweet.in_reply_to_status_id and self.generate_random_lock.locked():
            # This was a random tweet, so release lock (regardless of success)
            logger.debug("Releasing generate_random_lock")
            self.generate_random_lock.release()

    def _set_post_status_limit(self, subtract=0):
        if hasattr(self, "post_status_limit") and self.post_status_limit.reset > time.time():
            reset = self.post_status_limit.reset
            remaining = self.post_status_limit.remaining - subtract
        else:
            # We don't actually know when the reset is due, so we cautiously
            # assume it's 3 hours from now
            reset = int(time.time()) + settings.POST_STATUS_LIMIT_RESET_FREQUENCY
            remaining = settings.POST_STATUS_LIMIT - subtract
        self.post_status_limit = EndpointRateLimit(limit=settings.POST_STATUS_LIMIT, remaining=remaining, reset=reset)
        logger.debug(f"Set self.post_status_limit: {self.post_status_limit}")

    def _time_for_random_post(self):
        # Find the item in self.random_post_times that is closest to the
        # current time, counted backwards. If this item differs from the item
        # closest to the last time we posted, it's time to post again.
        # (Also, always return True if last post time was >= 24h ago.)
        def find_time_slot(ts: "Union[int, float]") -> "datetime.time":
            intime = datetime.datetime.fromtimestamp(ts).time()
            times = sorted(self.random_post_times, reverse=True)
            for idx, rt in enumerate(times):
                if rt <= intime:
                    return rt
                if idx == len(times) - 1:  # We have reached the last item in list
                    return times[0]

        now = int(time.time())
        last_random_post_time = self.db.posted_tweets.original_posts.latest_ts
        if last_random_post_time > (now - 24 * 60 * 60):
            return find_time_slot(last_random_post_time) != find_time_slot(time.time())
        return True
