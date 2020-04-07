# TwitterHAL

A MegaHAL Twitter bot in Python.

## Prerequisites

* Python 3
* [My fork of Chris Jones' Python MegaHAL](https://github.com/Eboreg/megahal)
* [bear/python-twitter](https://github.com/bear/python-twitter)
* [carpedm20/emoji](https://github.com/carpedm20/emoji/)
* [python-Levenshtein](https://github.com/ztane/python-Levenshtein)
* OPTIONAL: [detectlanguage](https://github.com/detectlanguage/detectlanguage-python)

But all those should be installed automatically by `pip` or `setup.py`. (`detectlanguage` is installed by using `pip install twitterhal[detectlanguage]`.)

## Usage

### Command line

`twitterhal -h` for usage.

`twitterhal --run` will post random tweets at `random_post_times` (see below), as well as answering all incoming mentions, all while trying its best not to exceed the [Twitter API rate limits](https://developer.twitter.com/en/docs/basics/rate-limits).

### As a library:

```python
from twitterhal import TwitterHAL
with TwitterHAL(screen_name="twitterhal", twitter_kwargs={"consumer_key": "foo", "consumer_secret": "bar"}) as hal:
    for mention in hal.get_mentions():
        hal.generate_reply(mention)
    hal.generate_random()
    hal.post_from_queue()
```

## Configuration

The command line util reads config from `./twitterhal.cfg`, `~/.config/twitterhal.cfg`, `./setup.cfg`, or whatever
filename you supply via the `-c` parameter. It's a standard INI file with these contents:

```ini
[twitterhal]
screen_name = twitterhal
random_post_times = 8:00, 16:00, 22:00  # OPTIONAL
include_mentions = true  # OPTIONAL
[twitter]
consumer_key = foo
consumer_secret = bar
access_token_key = boo
access_token_secret = far
[megahal]
brainfile = brain
order = 5
timeout = 30
banwordfile = banwords.txt
```

`[twitter]` contains keyword arguments for `twitter.Api`. Read more about it [here](https://python-twitter.readthedocs.io/en/latest/twitter.html).

`[megahal]` contains keyword arguments for `megahal.Megahal`. Consult that module for more info.

`include_mentions`: if `true`, TwitterHAL will include _all_ mentions in its replies. That is, not only the @handle of the user who wrote to it, but also every user they mentioned in their tweet. Perhaps you should use this carefully. Anyway, the default is `false`.

## Extending

You may extend TwitterHAL's database by subclassing `TwitterHAL` and adding `models.DatabaseItem` definitions to its `init_db()` method. Maybe you want to feed the MegaHAL brain by regularily fetching top tweets for trending topics, and need to keep track of those? I know I do.

By default, the database (which is of type `models.Database`) will contain:
* `posted_tweets` (`models.TweetList`): List of posted Tweets
* `mentions` (`models.TweetList`): List of tweets that mention us, and whether they have been answered
* `api_requests` (`Dict[str, List[int]]`): Keys are the different Twitter API endpoints (e.g. "statuses/mentions_timeline"), values are timestamps for the latest requests done to those endpoints. This is to try and make sure we don't exceed the rate limits. (They will, for the most part, be reset within 15 minutes, but who wants to be forced to wait that long?)

Tweets are internally stored in `models.TweetList`, which contains the method `only_in_language()`. This will filter out all tweets that are _probably_ in the chosen language, with the help of the [Language Detection API](https://detectlanguage.com/). Just install the PyPI package `detectlanguage`, get yourself an API key and feed it to `detectlanguage.configuration.api_key`, and you're all set.

If you extend TwitterHAL with new methods that call the Twitter API, it's recommended you also check TwitterHAL's `can_do_request(url)`, where `url` is something like `/statuses/mentions_timeline` (consult [this page](https://developer.twitter.com/en/docs/basics/rate-limits) for full list), to see whether this call should be made at this time.
