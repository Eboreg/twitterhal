import datetime

import megahal
import twitter


SCREEN_NAME = ""
RANDOM_POST_TIMES = [datetime.time(8), datetime.time(16), datetime.time(22)]
INCLUDE_MENTIONS = False
DATABASE_CLASS = "twitterhal.models.Database"
DATABASE_FILE = "twitterhal"
DETECTLANGUAGE_API_KEY = ""

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
    "timeout": megahal.DEFAULT_HARD_TIMEOUT,
    "banwords": megahal.DEFAULT_BANWORDS,
}
