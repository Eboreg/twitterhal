import pickle
import shelve
from collections import UserList
from datetime import datetime
from email.utils import formatdate
from threading import RLock

from Levenshtein import ratio  # pylint: disable=no-name-in-module
from twitter.models import Status

from twitterhal.conf import settings
from twitterhal.util import strip_phrase


class DatabaseItem:
    def __init__(self, type_, *default_args, is_list=False, **default_kwargs):
        self.type = type_
        self.is_list = is_list
        self.default_args = default_args
        self.default_kwargs = default_kwargs
        self.value = self.type(*default_args, **default_kwargs)

    def __setattr__(self, name, value):
        if name == "value" and not isinstance(value, self.type):
            raise TypeError
        super().__setattr__(name, value)


class Database:
    """Wrapper for typed `shelve` DB storing TwitterHAL data."""

    def __init__(self, db_path="twitterhal"):
        """Initialize the DB.

        Args:
            db_path (str, optional): Path to the .db file on disk, without
                extension. Default: "twitterhal"
        """
        self._is_open = False
        self._db_path = db_path
        self._lock = RLock()
        self._schema = {
            "posted_tweets": DatabaseItem(TweetList, is_list=True, unique=True),
            "mentions": DatabaseItem(TweetList, is_list=True, unique=True),
        }

    def add_key(self, name, type_, *default_args, **default_kwargs):
        assert not self._is_open, "Cannot add to schema once DB has been opened"
        self._schema[name] = DatabaseItem(type_, *default_args, **default_kwargs)

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *args, **kwargs):
        self.close()

    def __setattr__(self, name, value):
        if not name.startswith("_") and self._is_open:
            with self._lock:
                assert name in self._schema, "Key %s not present in DB schema" % name
                try:
                    self._schema[name].value = value
                except TypeError:
                    raise TypeError(f"{value} is of wrong type for {name}, should be: {self._schema[name].type}")
                self._db[name] = value
        super().__setattr__(name, value)

    def open(self):
        with self._lock:
            self._db = shelve.open(self._db_path)
            for k, v in self._schema.items():
                setattr(self, k, self._db.get(k, v.value))
            self._is_open = True

    def close(self):
        with self._lock:
            self.sync()
            self._db.close()
            self._is_open = False

    def sync(self):
        with self._lock:
            for key in self._schema.keys():
                self._db[key] = getattr(self, key)
            self._db.sync()


class _RedisListWrapper(UserList):
    def __init__(self, redis, type_, *default_args, **default_kwargs):
        self.redis = redis
        self.type = type_
        self.wrapped_list = self.type(*default_args, **default_kwargs)


class RedisListWrapper(UserList):
    def __init__(self, redis, key, initlist=None):
        self.redis = redis
        self.key = key
        if initlist is not None:
            if isinstance(initlist, UserList):
                self.data = initlist.data[:]
            else:
                self.data = list(initlist)

    @property
    def data(self):
        return [pickle.loads(i) for i in self.redis.lrange(self.key, 0, -1)]

    @data.setter
    def data(self, value):
        self.clear()
        if value:
            self.redis.rpush(self.key, *[pickle.dumps(i) for i in value])

    def __len__(self):
        return self.redis.llen(self.key)

    def __getitem__(self, i):
        value = self.redis.lindex(self.key, i)
        if value is None:
            raise IndexError("list index out of range")
        return pickle.loads(value)

    def __setitem__(self, i, item):
        from redis import ResponseError
        try:
            self.redis.lset(self.key, i, pickle.dumps(item))
        except ResponseError:
            raise IndexError("list assignment index out of range")

    def __delitem__(self, i):
        # Not safe for lists with duplicate elements
        value = self.redis.lindex(self.key, i)
        if value is None:
            raise IndexError("list assignment index out of range")
        self.redis.lrem(self.key, 1, value)

    def append(self, item):
        self.redis.rpush(self.key, pickle.dumps(item))

    def insert(self, i, item):
        # Not safe for lists with duplicate elements
        ref_item = self.redis.lindex(self.key, i)
        if ref_item is None:
            # Mimicking Python's list insert behaviour
            if i >= 0:
                self.append(item)
            else:
                self.redis.lpush(self.key, pickle.dumps(item))
        else:
            self.redis.linsert(self.key, "BEFORE", ref_item, pickle.dumps(item))

    def pop(self, i=-1):
        if i == -1:
            value = self.redis.rpop(self.key)
        elif i == 0:
            value = self.redis.lpop(self.key)
        else:
            value = self.redis.lindex(self.key, i)
            if value is None:
                raise IndexError("pop index out of range")
            self.redis.lrem(self.key, 1, value)
        return pickle.loads(value)

    def remove(self, item):
        count = self.redis.lrem(self.key, 1, pickle.dumps(item))
        if not count:
            raise ValueError("list.remove(x): x not in list")

    def clear(self):
        del self.redis[self.key]

    def extend(self, other):
        if isinstance(other, UserList):
            self.redis.rpush(self.key, *[pickle.dumps(i) for i in other.data])
        else:
            # List comprehension will throw TypeError if `other` is not
            # iterable, which is exactly what we want, since that is what
            # list.extend() also does
            self.redis.rpush(self.key, *[pickle.dumps(i) for i in other])

    # Methods that are not applicable, since they would require a new Redis
    # key to make any sense:
    def copy(self):
        raise NotImplementedError("Not applicable on a Redis list")

    def __add__(self, other):
        raise NotImplementedError("Not applicable on a Redis list")
    __radd__ = __add__
    __iadd__ = __add__
    __mul__ = __add__
    __rmul__ = __add__
    __imul__ = __add__


class RedisDatabase(Database):
    """
    self.posted_tweets m fl listor behöver kapslas in så att ändringar i
    deras medlemmar automatiskt uppdaterar databasen.
    Dessa är Redis-listor av picklade Tweet-objekt.
    "Unpicklas" här till sådana inkapslade TweetLists.
    """

    def __init__(self, **kwargs):
        self._is_open = False
        self._schema = {
            "posted_tweets": DatabaseItem(TweetList, TweetList(unique=True), is_list=True),
            "mentions": DatabaseItem(TweetList, TweetList(unique=True), is_list=True),
        }
        self._redis_kwargs = kwargs

    def __setattr__(self, name, value):
        if not name.startswith("_"):
            assert name in self._schema, "Key %s not present in DB schema" % name
            self._schema[name].value = value

            self._db[name] = value
        super().__setattr__(name, value)

    def __enter__(self):
        return self

    def __exit__(self, *args, **kwargs):
        self._db.close()
        self._is_open = False

    def open(self):
        from redis import Redis

        self._db = Redis(**self._redis_kwargs)
        for k, v in self._schema.items():
            if v.is_list:
                setattr(self, k, RedisListWrapper(self._db, v.type, *v.default_args, **v.default_kwargs))
            setattr(self, k, self._db.get(k, v.value))
        self._is_open = True


class Tweet(Status):
    """Extended version of Status from the `twitter` package.

    Not dependent on whether we run 'extended mode' or not; self.text will
    contain status.full_text if available, otherwise status.text.

    self.filtered_text: tweet text filtered by utils.strip_phrase().

    self.is_answered: tweet that mentions us, to denote whether it's been
        answered.
    self.is_processed: does not actually hold any meaning by default, but may
        be used for whatever purpose.
    """

    def __init__(self, is_answered=False, is_processed=False, filtered_text=None, **kwargs):
        super().__init__(**kwargs)
        self.text = self.full_text or self.text
        if filtered_text is None:
            self.filtered_text = strip_phrase(self.text or "")
        else:
            self.filtered_text = filtered_text
        self.is_answered = is_answered
        self.is_processed = is_processed
        self.created_at = self.created_at or formatdate()

    def __eq__(self, other):
        if issubclass(other.__class__, Status):
            return self.id == other.id
        return False

    def __repr__(self):
        if self.user:
            return f"Tweet<id={self.id}, screen_name={self.user.screen_name}, created={self.created_at}, " + \
                f"text={self.text}>"
        else:
            return f"<Tweet(id={self.id}, created={self.created_at}, text={self.text})>"

    def __str__(self):
        return repr(self)

    @classmethod
    def from_status(cls, status):
        kwargs = {}
        for param, default in status.param_defaults.items():
            kwargs[param] = getattr(status, param, default)
        return cls(**kwargs)


class TweetList(UserList):
    """A list of Tweet objects."""

    def __init__(self, initlist=None, unique=False):
        """Initialize the list.

        Args:
            initlist (list, optional): A list of Tweet objects
            unique (bool, optional): If True, the list will only contain
                unique Tweets, based on status ID
        """
        self.unique = unique
        self.data = []
        if initlist is not None:
            if self.unique:
                for t in initlist:
                    if t not in self.data:
                        self.data.append(t)
            else:
                self.data = initlist
        else:
            self.data = []

    def __setitem__(self, i, item):
        if not self.unique or item not in self.data:
            self.data[i] = item

    def __add__(self, other):
        if other.__class__ == self.__class__:
            other = other.data
        if self.unique:
            return self.__class__(self.data + [t for t in other if t not in self.data], unique=True)
        return self.__class__(self.data + other)

    def __radd__(self, other):
        if other.__class__ == self.__class__:
            other = other.data
            unique = other.unique
        if unique:
            return self.__class__(other + [t for t in self.data if t not in other], unique=True)
        return self.__class__(other + self.data)

    def __iadd__(self, other):
        if other.__class__ == self.__class__:
            other = other.data
        if self.unique:
            self.data += [t for t in other if t not in self.data]
        else:
            self.data += other
        return self

    def append(self, item):
        if self.unique or item not in self.data:
            self.data.append(item)

    def insert(self, i, item):
        if self.unique or item not in self.data:
            self.data.insert(i, item)

    def extend(self, other):
        if other.__class__ == self.__class__:
            other = other.data
        if self.unique:
            self.data.extend([t for t in other if t not in self.data])
        else:
            self.data.extend(other)

    def get_by_id(self, id):
        if not self.unique:
            raise ValueError("Refusing to run get_by_id() when unique == False")
        try:
            return [t for t in self.data if t.id == id][0]
        except IndexError:
            return None

    def only_in_language(self, language_code):
        """Filter for those Tweets that seem to be in a given language.

        Tweet language is decided by the `detectlanguage` API:
        https://detectlanguage.com/

        If detectlanguage.configuration.api_key has not already been set, tries
        to get it from settings.DETECTLANGUAGE_API_KEY.
        """
        import detectlanguage
        if detectlanguage.configuration.api_key is None:
            detectlanguage.configuration.api_key = settings.DETECTLANGUAGE_API_KEY
        if not isinstance(language_code, str):
            raise ValueError("language_code has to be string")
        result = []
        languages = detectlanguage.detect([tweet.filtered_text for tweet in self.data])
        for idx, lang in enumerate(languages):
            try:
                if lang[0]["language"] == language_code:
                    result.append(self.data[idx])
            except IndexError:
                pass
        self.data = result

    def remove_older_than(self, t):
        """Clears the list of Tweets older than a given value.

        Args:
            t (float, int, datetime): Remove all that are older than this;
                float or int is interpreted as UNIX timestamps.

        Returns:
            int: Number of items removed
        """
        if isinstance(t, datetime):
            t = t.timestamp()
        if not isinstance(t, (int, float)):
            raise ValueError("Argument must be a timestamp or datetime")
        old_count = len(self.data)
        self.data = [tweet for tweet in self.data if tweet.created_at_in_seconds >= t]
        return old_count - len(self.data)

    def fuzzy_duplicates(self, item):
        """Return TweetList of Tweets whose text is sufficiently similar to
        `item` (Levenshtein ratio > 0.8)
        """
        if isinstance(item, Status):
            item = Tweet.from_status(item)
        if isinstance(item, Tweet):
            string = item.filtered_text
        elif isinstance(item, str):
            string = strip_phrase(item)
        else:
            raise ValueError("item has to be str, Tweet, or Status")
        return self.__class__([t for t in self.data if ratio(t.filtered_text, string) > 0.8])

    @property
    def earliest_ts(self):
        return min([t.created_at_in_seconds for t in self.data], default=0)

    @property
    def latest_ts(self):
        return max([t.created_at_in_seconds for t in self.data], default=0)

    @property
    def earliest_date(self):
        ts = self.earliest_ts
        return datetime.fromtimestamp(ts) if ts > 0 else None

    @property
    def latest_date(self):
        ts = self.latest_ts
        return datetime.fromtimestamp(ts) if ts > 0 else None

    @property
    def processed(self):
        """Return TweetList of all Tweets that are flagged as processed"""
        return self.__class__([t for t in self.data if t.is_processed], unique=self.unique)

    @property
    def non_processed(self):
        """Return TweetList of all Tweets that are NOT flagged as processed"""
        return self.__class__([t for t in self.data if not t.is_processed], unique=self.unique)

    @property
    def answered(self):
        """Return TweetList of all Tweets that are flagged as replied"""
        return self.__class__([t for t in self.data if t.is_answered], unique=self.unique)

    @property
    def unanswered(self):
        """Return TweetList of all Tweets that are NOT flagged as replied"""
        return self.__class__([t for t in self.data if not t.is_answered], unique=self.unique)

    @property
    def original_posts(self):
        """Return TweetList of all Tweets that are original posts, i.e. NOT
        replies to another tweet
        """
        return self.__class__([t for t in self.data if t.in_reply_to_status_id is None], unique=self.unique)

    @property
    def replies(self):
        """Return TweetList of all Tweets that are replies to another tweet"""
        return self.__class__([t for t in self.data if t.in_reply_to_status_id is not None], unique=self.unique)
