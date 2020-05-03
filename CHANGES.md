# Changelog

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
