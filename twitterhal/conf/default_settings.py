import datetime
import pickle
from copy import deepcopy

from twitter.api import CHARACTER_LIMIT


_DATABASE_REDIS = {
    "class": "twitterhal.database.RedisDatabase",
    "options": {
        "host": "localhost",
        "pickle_protocol": pickle.DEFAULT_PROTOCOL,
        "namespace": "twitterhal",
        "port": 6379,
        "db": 0,
    },
    "test_options": {
        "namespace": "twitterhal:test",
    },
}
_MEGAHAL_DATABASE_REDIS = deepcopy(_DATABASE_REDIS)
_MEGAHAL_DATABASE_REDIS["options"]["namespace"] = "twitterhal:megahal"
_MEGAHAL_DATABASE_REDIS["test_options"]["namespace"] = "twitterhal:test:megahal"

_DATABASE_SHELVE = {
    "class": "twitterhal.database.ShelveDatabase",
    "options": {
        "db_path": "twitterhal",
    },
    "test_options": {
        "db_path": "twitterhal.test",
    },
}
_MEGAHAL_DATABASE_SHELVE = deepcopy(_DATABASE_SHELVE)
_MEGAHAL_DATABASE_SHELVE["options"]["db_path"] = "twitterhal.brain"
_MEGAHAL_DATABASE_SHELVE["test_options"]["db_path"] = "twitterhal.test.brain"

DATABASE = _DATABASE_SHELVE
DETECTLANGUAGE_API_KEY = ""
INCLUDE_MENTIONS = False
MEGAHAL_DATABASE = _MEGAHAL_DATABASE_SHELVE
POST_STATUS_LIMIT = 300
POST_STATUS_LIMIT_RESET_FREQUENCY = 3 * 60 * 60
RANDOM_POST_TIMES = [datetime.time(8), datetime.time(16), datetime.time(22)]
RUNNER_SLEEP_SECONDS = 5
SCREEN_NAME = ""

# List of Twitter handles we will never mention (including replying to them).
# Without "@"!
BANNED_USERS = []

TWITTER_API = {
    "consumer_key": "",
    "consumer_secret": "",
    "access_token_key": "",
    "access_token_secret": "",
    "timeout": 40,
    "tweet_mode": "extended",
}

MEGAHAL_API = {
    "max_length": CHARACTER_LIMIT,
    # Only applies to version <0.4.0 of megahal:
    "brainfile": "twitterhal-brain",
}
