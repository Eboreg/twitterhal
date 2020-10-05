# Changelog

## v0.7.3 (2020-10-05)

Fixed bug where multiple instances of MegaHAL would be started simultaneously

## v0.7.2 (2020-09-06)

Note: 0.7.1 was redacted for still containing bugs.

### Changes:

* `runtime.LoopTask` now checks if the running task has gone on for more than a customizable number of seconds (default: 120), in that case concludes it's has hung and runs the task anyway

## v0.7.0 (2020-05-16)

### Changes:

* `database.RedisList` now doesn't use an in-memory cache.
* Instantiation of `database.RedisList` actually creates a subclass, that transparently implements any custom methods on the provided `initlist` or `list_type`.

## v0.6.2 (2020-05-04)

### Bugfixes:

* `TwitterHAL.generate_tweet()` didn't include suffix in length calculation when retrying. Now fixed.

## v0.6.1 (2020-05-04)

### Changes:

* `runtime.LoopTask` now logs raised exceptions

### Bugfixes:

* `RedisDatabase.__setattr__()` now checks for `list` values and turns them into `RedisList` where applicable

## v0.6.0 (2020-05-03)

### Changes:

* Factored out DB stuff to `twitterhal.database`
* Added (optional) `namespace` option to `RedisDatabase`. If set, Redis keys will have the format `namespace:key`. Default namespace value is `twitterhal`.

## v0.5.7 (2020-05-03)

### Changes:

* Adding keys to DB schema in `TwitterHAL.init_db()` instead of "hard-coding" them in `models.BaseDatabase`

## v0.5.6 (2020-05-03)

### Changes:

* Not checking uniqueness when `TweetList.data` is redefined; took too much time. Instead made `Tweet` hashable and added uniqueness check in `RedisList.wrap()` if unique=True is submitted.

## v0.5.5 (2020-05-01)

### Bugfixes:

* Removed over-optimization in `RedisList` which would sometimes cause changed data not to get saved

## v0.5.4 (2020-05-01)

* Started writing changelog, so can't really report anything :o)
