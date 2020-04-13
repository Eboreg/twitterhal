import datetime
import logging
import queue
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from typing import cast

import twitter
from megahal import MegaHAL
from twitter.api import CHARACTER_LIMIT
from twitter.ratelimit import EndpointRateLimit

from twitterhal.conf import settings
from twitterhal.gracefulkiller import GracefulKiller
from twitterhal.models import Tweet, TweetList

logger = logging.getLogger(__name__)

POST_STATUS_LIMIT = 300
POST_STATUS_LIMIT_RESET_FREQUENCY = 3 * 60 * 60


class TwitterHAL:
    def __init__(self, screen_name=None, random_post_times=None, include_mentions=None, **kwargs):
        """Initialize the bot.

        If not explicitly overridden here, arguments will be collected from
        `twitterhal.conf.settings`.

        Args:
            screen_name (str): Twitter screen name ("handle") for this bot
                (without the '@'!)
            random_post_times (list of datetime.time, optional): The times of
                day when random posts will be done. Defaults to 8:00, 16:00,
                and 22:00.
            include_mentions (bool, optional): Whether to include all
                @mentions in our replies, and not only that of the user we're
                replying to
        """
        # Take care of settings
        self.twitter_kwargs = self.get_twitter_api_kwargs()
        self.megahal_kwargs = self.get_megahal_api_kwargs()
        self.screen_name = screen_name or settings.SCREEN_NAME
        self.random_post_times = random_post_times or settings.RANDOM_POST_TIMES
        self.include_mentions = include_mentions or settings.INCLUDE_MENTIONS

        # Set up runtime stuff
        Database = settings.get_database_class()
        self.db = cast("DBInstance", Database())
        self.queue = queue.Queue()
        self.exit_event = threading.Event()
        self.generate_random_lock = threading.Lock()
        self.learn_phrases_lock = threading.Lock()  # not used?
        self.megahal_open = False

    def get_twitter_api_kwargs(self, **kwargs):
        defaults = deepcopy(settings.TWITTER_API)
        defaults.update(kwargs)
        return defaults

    def get_megahal_api_kwargs(self, **kwargs):
        defaults = deepcopy(settings.MEGAHAL_API)
        defaults.update(kwargs)
        return defaults

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *args, **kwargs):
        self.close()
        logger.info("Exited gracefully =)")

    def open(self):
        logger.info("Starting engine ...")
        try:
            logger.debug("Initializing Twitter API ...")
            self.api = twitter.Api(**self.twitter_kwargs)
        except Exception as e:
            logger.error(str(e), exc_info=True)
            raise e
        self.init_db()
        self._init_post_status_limit()
        logger.info("Ready!")

    def close(self):
        logger.info("Closing DB ...")
        self.db.close()
        if self.megahal_open:
            logger.info("Closing MegaHAL ...")
            self.megahal.close()
            self.megahal_open = False

    @property
    def megahal(self):
        if not self.megahal_open:
            logger.info("Initializing MegaHAL ...")
            self._megahal = MegaHAL(**self.megahal_kwargs)
            self.megahal_open = True
        return self._megahal

    """ ---------- SINGLETON WORKERS TO BE RUN CONTINUOUSLY ---------- """

    def post_tweets_worker(self):
        """
        Worker that continuously fetches Tweet objects from self.queue and
        posts them.
        """
        while not self.exit_event.is_set() or not self.queue.empty():
            if self.can_post():
                try:
                    tweet: "Tweet" = self.queue.get(timeout=1)
                except queue.Empty:
                    continue
                logger.debug("Got from queue: %s", tweet)
                self._post_tweet(tweet)
        logger.debug("Recevied exit event")

    """ ---------- OTHER METHODS TO BE USED IN "DAEMON" LOOP ---------- """

    def generate_random(self):
        """Generate a random tweet and put it in queue

        Using Lock to prevent two random tweet being generated
        simultaneously. Lock is released by _post_tweet() after post
        has been attempted (whether it succeeded or not).
        """
        if not self._time_for_random_post():
            logger.debug("Not yet time for random post")
            pass
        elif not self.generate_random_lock.acquire(blocking=False):
            logger.debug("Could not acquire lock")
        else:
            logger.info("Generating new random tweet ...")
            tweet = self.generate_tweet()
            logger.debug("Putting random tweet in queue: %s", tweet)
            self.queue.put(tweet)

    def generate_reply(self, mention):
        """Generate reply Tweet for a mention Tweet, put it in post queue"""
        # We trust that no generate_reply to this particular mention has
        # already been started (checked in get_new_mentions())
        logger.debug("Generating reply to %s", mention.text)
        reply = self.generate_tweet(in_reply_to=mention)
        logger.debug("Putting reply in queue: %s", reply)
        self.queue.put(reply)

    def get_new_mentions(self):
        """Fetch new (unanswered) Tweets mentioning us

        Add new mentions to self.db.mentions, if they are not already in there.
        Then returns a TweetList of new mentions, where "new" actually means
        "those we haven't answered yet".

        TODO: Separate "new" from "unanswered" mentions?
        """
        if not self.can_do_request("/statuses/mentions_timeline"):
            return TweetList()
        try:
            self.db.mentions.extend(
                [Tweet.from_status(m) for m in self.api.GetMentions() if m not in self.db.mentions]
            )
        except twitter.TwitterError as e:
            logger.error(str(e), exc_info=True)
            return TweetList()
        else:
            for mention in self.db.mentions.unanswered:
                logger.info("Got new mention: %s", mention.text)
            return self.db.mentions.unanswered

    """ ---------- VARIOUS PUBLIC METHODS ---------- """

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
        return limit.remaining >= count

    def can_post(self, count=1):
        if self.post_status_limit.reset <= time.time():
            self._set_post_status_limit()
        return self.post_status_limit.remaining >= count

    def generate_tweet(self, in_reply_to=None):
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

        Returns:
            models.Tweet object
        """
        start_time = datetime.datetime.now().time().isoformat("seconds")
        if in_reply_to:
            prefixes = ["@" + in_reply_to.user.screen_name]
            if self.include_mentions:
                prefixes += [
                    # Negative lookbehind to avoid matching email addresses
                    h for h in re.findall(r"(?<!\w)@[a-z0-9_]+", in_reply_to.text, flags=re.IGNORECASE)
                    if h.lower() not in ["@" + self.screen_name, "@" + in_reply_to.user.screen_name.lower()]
                ]
            prefix = " ".join(prefixes) + " "
        else:
            prefix = ""
        phrase = in_reply_to.filtered_text if in_reply_to else ""
        reply = self.megahal.get_reply(phrase, max_length=CHARACTER_LIMIT - len(prefix))
        while not reply or self.db.posted_tweets.fuzzy_duplicates(reply):
            # If, for some reason, we got an empty or duplicate reply: keep
            # trying, but don't learn from the input again
            if not reply:
                logger.info("Got empty reply, trying again (since %s)", start_time)
            else:
                logger.info("Got duplicate reply, trying again (since %s): %s", start_time, reply)
            reply = self.megahal.get_reply_nolearn(phrase, max_length=CHARACTER_LIMIT - len(prefix))
        tweet = Tweet(
            text=prefix + reply.text,
            in_reply_to_status_id=in_reply_to.id if in_reply_to is not None else None
        )
        return tweet

    def init_db(self):
        """Initialize TwitterHAL database

        If you extend the functionality and want to store additional values in
        the DB, this is the place to define them. Just do:

        >>> self.db.add_key(key_name, key_type, key_default)
        >>> super().init_db()
        """
        logger.debug("Trying to initialize DB ...")
        self.db.open()
        # Just for safety:
        random_tweets = self.api.GetUserTimeline(screen_name=self.screen_name, exclude_replies=True, count=1)
        if len(random_tweets) > 0 and random_tweets[0] not in self.db.posted_tweets:
            self.db.posted_tweets.append(Tweet.from_status(random_tweets[0]))
        logger.debug("DB initialized")

    def post_from_queue(self):
        """Post all queued Tweets

        Not used in the regular loop, exists more like a little helper for
        those who may want it. Simply loops through the internal queue of
        Tweets and posts them.
        """
        while not self.queue.empty():
            tweet: "Tweet" = self.queue.get()
            logger.debug("Got from queue: %s", tweet)
            self._post_tweet(tweet)

    """ ---------- PRIVATE HELPER METHODS ---------- """

    def _init_post_status_limit(self):
        """Initialize status/retweet post limit data

        Since Twitter API for some reason doesn't supply these numbers, we
        make an effort to keep track of them ourselves, going after the limits
        specified at:
        https://developer.twitter.com/en/docs/tweets/post-and-engage/api-reference/post-statuses-retweet-id
        """
        since = time.time() - 3 * 60 * 60
        latest_posts = self.api.GetUserTimeline(screen_name=self.screen_name, count=200, trim_user=True)
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
            status = self.api.PostUpdate(
                tweet.filtered_text, in_reply_to_status_id=tweet.in_reply_to_status_id)
        except Exception as e:
            logger.error(str(e), exc_info=True)
        else:
            # Logging the request here, since I guess it counts towards
            # the rate limit whether we succeed or not
            self._set_post_status_limit(subtract=1)
            self.db.posted_tweets.append(Tweet.from_status(status))
            if tweet.in_reply_to_status_id:
                # This was a reply to a mention
                original_tweet = self.db.mentions.get_by_id(tweet.in_reply_to_status_id)
                if original_tweet:
                    original_tweet.is_answered = True
            logger.info("Posted: %s", tweet)
        if not tweet.in_reply_to_status_id and self.generate_random_lock.locked():
            # This was a random tweet, so release lock (whether post
            # succeeded or not)
            logger.debug("Releasing generate_random_lock")
            self.generate_random_lock.release()

    def _set_post_status_limit(self, subtract=0):
        if hasattr(self, "post_status_limit") and self.post_status_limit.reset > time.time():
            reset = self.post_status_limit.reset
            remaining = self.post_status_limit.remaining - subtract
        else:
            # We don't actually know when the reset is due, so we cautiously
            # assume it's 3 hours from now
            reset = int(time.time()) + POST_STATUS_LIMIT_RESET_FREQUENCY
            remaining = POST_STATUS_LIMIT - subtract
        self.post_status_limit = EndpointRateLimit(limit=POST_STATUS_LIMIT, remaining=remaining, reset=reset)

    def _time_for_random_post(self):
        # Find the item in self.random_post_times that is closest to the
        # current time, counted backwards. If this item differs from the item
        # closest to the last time we posted, it's time to post again.
        # (Also, always return True if last post time was >= 24h ago.)
        def find_time_slot(ts: "Union[int, float]") -> "datetime.time":  # type: ignore[return]
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


def run(hal):
    killer = GracefulKiller()
    with ThreadPoolExecutor() as executor:
        logger.info("Starting post_tweets_worker thread ...")
        post_tweets_worker = executor.submit(hal.post_tweets_worker)
        while not killer.kill_now:
            logger.debug("Running generate_random and get_new_mentions ...")
            executor.submit(hal.generate_random)
            for mention in hal.get_new_mentions():
                logger.debug("Submitting generate_reply for %s", mention)
                executor.submit(hal.generate_reply, mention)
            killer.sleep(15)
            if not post_tweets_worker.running():
                exc = post_tweets_worker.exception()
                if exc is not None:
                    logger.error("post_tweets_worker raised exception: %s. Restarting ...", str(exc))
                else:
                    logger.error("post_tweets_worker thread exited without exception! Restarting ...")
                if hal.generate_random_lock.locked():
                    hal.generate_random_lock.release()
                post_tweets_worker = executor.submit(hal.post_tweets_worker)
        logger.debug("Setting exit_event")
        hal.exit_event.set()
        logger.info("Waiting for threads to finish ...")
    logger.info("Waiting for TwitterHAL to finish ...")
