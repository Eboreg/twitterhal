import datetime
import pickle

import megahal
import twitter


DATABASE_REDIS = {
    "class": "twitterhal.models.RedisDatabase",
    "options": {
        "host": "localhost",
        "port": 6379,
        "db": 0,
    },
    "test_options": {
        "db": 15,
    },
}
DATABASE_SHELVE = {
    "class": "twitterhal.models.ShelveDatabase",
    "options": {
        "db_path": "twitterhal",
    },
    "test_options": {
        "db_path": "test",
    },
}

DATABASE = DATABASE_SHELVE
DETECTLANGUAGE_API_KEY = ""
INCLUDE_MENTIONS = False
PICKLE_PROTOCOL = pickle.DEFAULT_PROTOCOL
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
    "max_length": twitter.api.CHARACTER_LIMIT,
    "brainfile": "twitterhal-brain",
    "order": megahal.DEFAULT_ORDER,
    "timeout": megahal.DEFAULT_TIMEOUT,
    "banwords": megahal.DEFAULT_BANWORDS,
}
