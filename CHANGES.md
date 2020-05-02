# Changelog

## v0.5.6 (2020-05-03)

### Changes:

* Not checking uniqueness when TweetList.data is redefined; took too much time. Instead made Tweet hashable and added uniqueness check in RedisList.wrap() if unique=True is submitted.

## v0.5.5 (2020-05-01)

### Bugfixes:

* Removed over-optimization in RedisList which would sometimes cause changed data not to get saved

## v0.5.4 (2020-05-01)

* Started writing changelog, so can't really report anything :o)
