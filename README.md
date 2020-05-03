# TwitterHAL

A MegaHAL Twitter bot in Python.

**This project is in alpha, and should NOT be considered stable in any way.**

Live examples (in Swedish): [@bibel3000](https://twitter.com/bibel3000), [@trendhal3000](https://twitter.com/trendhal3000)

## Prerequisites

* Python >= 3.6
* [My fork of Chris Jones' Python MegaHAL](https://github.com/Eboreg/megahal)
* [bear/python-twitter](https://github.com/bear/python-twitter)
* [carpedm20/emoji](https://github.com/carpedm20/emoji/)
* [python-Levenshtein](https://github.com/ztane/python-Levenshtein)
* OPTIONAL: [detectlanguage](https://github.com/detectlanguage/detectlanguage-python)
* OPTIONAL: [redis-py](https://github.com/andymccurdy/redis-py)

But all those should be installed automatically by `pip` or `setup.py`.

Use `pip install twitterhal[detectlanguage]` to install `detectlanguage`, `pip install twitterhal[redis]` to install `redis-py`.

## Usage

### Command line

```
$ twitterhal
usage: twitterhal [-s SETTINGS_MODULE] [-d] [-m] [-f] [-t]
                  [-r | --chat | --stats | --print-config | --post-random | --version]

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
  --version             Show program's version number and exit
```

`twitterhal --run` will post random tweets at `random_post_times` (see below), as well as answering all incoming mentions, all while trying its best not to exceed the [Twitter API rate limits](https://developer.twitter.com/en/docs/basics/rate-limits).

### As a library

```python
from twitterhal import TwitterHAL
with TwitterHAL(screen_name="twitterhal") as hal:
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
DATABASE = {
    "class": "path.to.DatabaseClass",
    "options": {},
    "test_options": {},
}
BANNED_USERS = ["my_other_twitterhal_bot"]
RUNNER_SLEEP_SECONDS = 5
POST_STATUS_LIMIT = 300
POST_STATUS_LIMIT_RESET_FREQUENCY = 3 * 60 * 60

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
    "timeout": megahal.DEFAULT_TIMEOUT,
    "banwords": ["MOST", "COMMON", "WORDS"],
}
```

`BANNED_USERS`: List of Twitter usernames (handles), without leading "@". We will never respond to, or mention, these users. Useful if you, for example, run two bots and don't want them to get stuck in an eternal loop responding to each other. (Perhaps, someday, I will figure out a clever way to detect such loops automatically.)

`DATABASE`: A dict of info about the database backend. Must at least contain the key `class`, which must be the path of a class inheriting from `database.BaseDatabase`. Included are `database.ShelveDatabase` and `database.RedisDatabase`. The `options` key contains kwargs to be sent to that database class' `__init__()` method. When TwitterHAL is run with the `--test` option, the options will be extended with the contents of the `test_options` dict.

`INCLUDE_MENTIONS`: if `True`, TwitterHAL will include _all_ mentions in its replies. That is, not only the @handle of the user who wrote to it, but also every user they mentioned in their tweet. Perhaps you should use this carefully. Anyway, the default is `False`.

`MEGAHAL` contains keyword arguments for `megahal.Megahal`. Consult [that module](https://pypi.org/project/megahal/) for more info.

`MEGAHAL_API["banwords"]`: you may want to set this if your bot will not be speaking English. Pro tip: search for a list of the ~300 most commonly used words in your language, and use those.

`POST_STATUS_LIMIT` and `POST_STATUS_LIMIT_RESET_FREQUENCY`: For some reason, Twitter's API doesn't provide info about the current ratio limits for posting tweets (and retweets), so I had to implement that check myself to my best ability. The numbers are taken from [here](https://developer.twitter.com/en/docs/basics/rate-limits).

`RANDOM_POST_TIMES`: TwitterHAL will post a randomly generated tweet on those points of (local) time every day. Default: 8:00, 16:00, and 22:00 (that is 8 AM, 4 PM and 10 PM, for those of you stuck in antiquity).

`RUNNER_SLEEP_SECONDS`: The interval with which `runtime.runner` starts its _loop tasks_. See below.

`TWITTER_API` contains keyword arguments for `twitter.Api`. Read more about it [here](https://python-twitter.readthedocs.io/en/latest/twitter.html).

## Extending

### Persistent storage

You may extend TwitterHAL's database by subclassing `TwitterHAL` and adding `database.DatabaseItem` definitions to its `init_db()` method. Maybe you want to feed the MegaHAL brain by regularily fetching top tweets for trending topics, and need to keep track of those? I know I do.

By default, the database (which is a subtype of `database.BaseDatabase`) will contain:
* `posted_tweets` (`models.TweetList`): List of posted Tweets
* `mentions` (`models.TweetList`): List of tweets that mention us, and whether they have been answered

### Language detection

Tweets are internally stored in `models.TweetList`, which contains the method `only_in_language()`. This will filter out all tweets that are _probably_ in the chosen language, with the help of the [Language Detection API](https://detectlanguage.com/). Just `pip install detectlanguage`, get yourself an API key and feed it to `detectlanguage.configuration.api_key` (or set it in your settings; see above), and you're all set.

### Twitter API calls

If you extend TwitterHAL with new methods that call the Twitter API, it's recommended you also check TwitterHAL's `can_do_request(url)`, where `url` is something like `/statuses/mentions_timeline` (consult [this page](https://developer.twitter.com/en/docs/basics/rate-limits) for full list), to see whether this call should be made at this time.

### Runtime

The "daemon" (not really a daemon) `twitterhal.runtime.runner`, invoked by `twitterhal --run`, does these things:

1. Starts _workers_, which will run continuously in separate threads
2. With an interval of `settings.RUNNER_SLEEP_SECONDS` seconds (default: 5), runs _loop tasks_, each in a new thread
3. On exit, runs _post loop tasks_

_Workers_ are registered by `TwitterHAL.register_workers()` through `runner.register_worker()`, and should be callables that loop until interrupted by a signal (see _GracefulKiller_ section below). If they accept the boolean keyword argument `restart`, they will be executed with `restart=True` in case they exited prematurely and had to be restarted by the runner.

_Loop tasks_, unlike workers, should be finite in time. They are registered by `TwitterHAL.register_loop_tasks()` through `runner.register_loop_task()`, are run max once per loop, and can be any callable. If `runner.register_loop_task()` is called with the integer argument `sleep` (seconds), `GracefulKiller.sleep()` (see below) will be called at the end of every execution of this task, and the runner will be prohibited from starting new executions of the task until this one has finished. (If you don't want it to sleep at the end, but still want to block the task from being run multiple times concurrently, send `sleep=0`.)

_Post loop tasks_ are registrered by `TwitterHAL.register_post_loop_tasks()` through `runner.register_post_loop_task()`, and can be any callable. They are called after the loop has been interrupted, and are _not_ run in separate threads. Useful for various clean-up actions. By default, there are none.

### GracefulKiller

`gracefulkiller.killer` is an object that listens for `SIGINT` and `SIGTERM` signals, whereupon its `kill_now` attribute is set to `True`. It also has a `sleep()` method, that mimics `time.sleep()` but aborts max 1 second after one of the aforementioned signals has been caught. `sleep()` returns `True` if `SIGALRM` was caught sometime during the sleeping, which could be used for pinging. Feel free to use this in your _workers_, _loop tasks_, etc.

Example:

```python
from twitterhal.gracefulkiller import killer

def hello_world_worker():
    while not killer.kill_now:
        print("Hello, world!")
        ping = killer.sleep(10)
        if ping:
            print("Pong!")
```

## Q & A

> Why doesn't TwitterHAL see all my mentions?

Twitter has a setting called "quality filter", which is said to "filter lower-quality content from your notifications", and is turned on by default. You can go to your bot's [notifications settings](https://twitter.com/settings/notifications) and uncheck the "Quality filter" checkbox (at least, that's how you did it 2020-04-24). This should solve it.
