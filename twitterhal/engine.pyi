import datetime
import queue
import threading
from typing import Any, Dict, Optional, Sequence

import twitter
from megahal import MegaHAL
from twitter.ratelimit import EndpointRateLimit

from twitterhal.models import Database, Tweet, TweetList


class DBInstance(Database):
    posted_tweets: TweetList
    mentions: TweetList


class TwitterHAL:
    api: twitter.Api
    megahal: MegaHAL
    post_status_limit: EndpointRateLimit
    twitter_kwargs: Dict[str, Any]
    megahal_kwargs: Dict[str, Any]
    screen_name: str
    random_post_times: Sequence[datetime.time]
    include_mentions: bool
    db: DBInstance
    queue: queue.Queue
    exit_event: threading.Event
    generate_random_lock: threading.Lock
    megahal_open: bool
    force: bool

    def __init__(
        self,
        screen_name: Optional[str],
        random_post_times: Optional[Sequence[datetime.time]],
        include_mentions: Optional[bool],
        init_megahal: bool,
        force: bool,
        **kwargs
    ):
        ...

    def __enter__(self) -> TwitterHAL:
        ...

    def __exit__(self, *args, **kwargs):
        ...

    def get_twitter_api_kwargs(self, **kwargs) -> Dict[str, Any]:
        ...

    def get_megahal_api_kwargs(self, **kwargs) -> Dict[str, Any]:
        ...

    def generate_reply(self, mention: Tweet):
        ...

    def get_new_mentions(self) -> TweetList:
        ...

    def can_do_request(self, url: str, count: int = 1) -> bool:
        ...

    def can_post(self, count: int = 1) -> bool:
        ...

    def generate_tweet(self, in_reply_to: Optional[Tweet] = None) -> Tweet:
        ...

    def _post_tweet(self, tweet: Tweet):
        ...

    def _set_post_status_limit(self, subtract: int):
        ...

    def _time_for_random_post(self) -> bool:
        ...


def run(hal: TwitterHAL):
    ...
