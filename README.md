# TwitterHAL

A MegaHAL Twitter bot in Python.

**This project is in alpha, and NOT considered stable in any way.**

Live examples (in Swedish): [@bibel3000](https://twitter.com/bibel3000), [@trendhal3000](https://twitter.com/trendhal3000)

## Prerequisites

* Python >= 3.6
* [My fork of Chris Jones' Python MegaHAL](https://github.com/Eboreg/megahal)
* [bear/python-twitter](https://github.com/bear/python-twitter)
* [carpedm20/emoji](https://github.com/carpedm20/emoji/)
* [python-Levenshtein](https://github.com/ztane/python-Levenshtein)
* OPTIONAL: [detectlanguage](https://github.com/detectlanguage/detectlanguage-python)

But all those should be installed automatically by `pip` or `setup.py`. (`detectlanguage` is installed by using `pip install twitterhal[detectlanguage]`.)

## Usage

### Command line

```
$ twitterhal
usage: twitterhal [-s SETTINGS_MODULE] [-d] [-m] [-f] [-t]
                  [-r | --chat | --stats | --print-config | --post-random]

optional arguments:
  -s SETTINGS_MODULE, --settings SETTINGS_MODULE
                        Python path to settings module. If omitted, we try
                        looking for it in the 'TWITTERHAL_SETTINGS_MODULE'
                        environment variable.
  -d, --debug           More verbose logging output
  -m, --include-mentions
                        Include all mentions in replies (rather than just the
                        handle we're replying to)
  -f, --force           Try and force stuff, even if TwitterHAL doesn't want
                        to
  -t, --test            Test mode; doesn't actually post anything
  -r, --run             Run the bot!
  --chat                Chat with the bot
  --stats               Display some stats
  --print-config        Print current parsed config
  --post-random         Post a new random tweet
```

`twitterhal --run` will post random tweets at `random_post_times` (see below), as well as answering all incoming mentions, all while trying its best not to exceed the [Twitter API rate limits](https://developer.twitter.com/en/docs/basics/rate-limits).

### As a library

```python
from twitterhal import TwitterHAL
with TwitterHAL(screen_name="twitterhal", twitter_kwargs={"consumer_key": "foo", "consumer_secret": "bar"}) as hal:
    for mention in hal.get_new_mentions():
        hal.generate_reply(mention)
    hal.generate_random()
    hal.post_from_queue()
```

## Configuration

Settings are read from a Python module specified in the `TWITTERHAL_SETTINGS_MODULE` environment variable, or whatever module you supply to the command-line utility via the `[-s | --settings]` parameter.

Some example settings:

```python
SCREEN_NAME = "my_k3wl_twitter_user"
RANDOM_POST_TIMES = [datetime.time(8), datetime.time(16), datetime.time(22)]
INCLUDE_MENTIONS = True
DETECTLANGUAGE_API_KEY = ""
DATABASE_CLASS = "twitterhal.models.Database"

TWITTER_API = {
    "consumer_key": "foo",
    "consumer_secret": "bar",
    "access_token_key": "boo",
    "access_token_secret": "far",
    "timeout": 40,
    "tweet_mode": "extended",
}

MEGAHAL_API = {
    "max_length": twitter.api.CHARACTER_LIMIT,
    "brainfile": "twitterhal-brain",
    "order": megahal.DEFAULT_ORDER,
    "timeout": megahal.DEFAULT_HARD_TIMEOUT,
    "banwords": ["MOST", "COMMON", "WORDS"],
}
```

`TWITTER_API` contains keyword arguments for `twitter.Api`. Read more about it [here](https://python-twitter.readthedocs.io/en/latest/twitter.html).

`MEGAHAL` contains keyword arguments for `megahal.Megahal`. Consult [that module](https://pypi.org/project/megahal/) for more info.

`RANDOM_POST_TIMES`: TwitterHAL will post a randomly generated tweet on those points of (local) time every day. Default: 8:00, 16:00, and 22:00 (that is 8 AM, 4 PM and 10 PM, for those of you stuck in antiquity).

`INCLUDE_MENTIONS`: if `True`, TwitterHAL will include _all_ mentions in its replies. That is, not only the @handle of the user who wrote to it, but also every user they mentioned in their tweet. Perhaps you should use this carefully. Anyway, the default is `False`.

`MEGAHAL_API["banwords"]`: you may want to set this if your bot will not be speaking English. Pro tip: search for a list of the ~300 most commonly used words in your language, and use those.

## Extending

You may extend TwitterHAL's database by subclassing `TwitterHAL` and adding `models.DatabaseItem` definitions to its `init_db()` method. Maybe you want to feed the MegaHAL brain by regularily fetching top tweets for trending topics, and need to keep track of those? I know I do.

By default, the database (which is of type `models.Database`) will contain:
* `posted_tweets` (`models.TweetList`): List of posted Tweets
* `mentions` (`models.TweetList`): List of tweets that mention us, and whether they have been answered

Tweets are internally stored in `models.TweetList`, which contains the method `only_in_language()`. This will filter out all tweets that are _probably_ in the chosen language, with the help of the [Language Detection API](https://detectlanguage.com/). Just install the PyPI package `detectlanguage`, get yourself an API key and feed it to `detectlanguage.configuration.api_key` (or set it in your settings; see above), and you're all set.

If you extend TwitterHAL with new methods that call the Twitter API, it's recommended you also check TwitterHAL's `can_do_request(url)`, where `url` is something like `/statuses/mentions_timeline` (consult [this page](https://developer.twitter.com/en/docs/basics/rate-limits) for full list), to see whether this call should be made at this time.
