import logging
import pickle
import shelve
from collections import UserList
from datetime import datetime
from email.utils import formatdate
from threading import RLock

from Levenshtein import ratio
from twitter.models import Status

from twitterhal.conf import settings
from twitterhal.util import strip_phrase


logger = logging.getLogger(__name__)


class DatabaseItem:
    def __init__(self, type_, **defaults):
        self.type = type_
        self.defaults = defaults


class BaseDatabase:
    def __init__(self):
        """Initialize the DB."""
        self._is_open = False
        self._schema = {
            "posted_tweets": DatabaseItem(TweetList, unique=True),
            "mentions": DatabaseItem(TweetList, unique=True),
        }

    def add_key(self, name, type_, **defaults):
        """Add new key to database

        Args:
            name (str): Name of the key. The value will be available as
                self.`name` on this object.
            type_ (type): Type of object stored under this key
        """
        self._schema[name] = DatabaseItem(type_, **defaults)

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *args, **kwargs):
        self.close()

    def __setattr__(self, name, value):
        if not name.startswith("_"):
            assert name in self._schema, "Key %s not present in DB schema" % name
            assert isinstance(value, self._schema[name].type), \
                f"'{value}' is of wrong type for '{name}', should be: '{self._schema[name].type.__name__}'"
            self.setattr(name, value)
        super().__setattr__(name, value)

    def setattr(self, name, value):
        """Hook for setting DB values

        Please override this one instead of __setattr__. This will ensure
        checks for key's existence in schema, and value being of the correct
        type, are always made.
        """
        raise NotImplementedError

    def open(self):
        """Hook for opening DB

        Make sure this sets self._is_open=True on success.
        """
        raise NotImplementedError

    def close(self):
        """Hook for closing DB

        If your close method doesn't call super().close(), make sure it sets
        self._is_open=False.
        """
        self._is_open = False
        for key in self._schema.keys():
            delattr(self, key)

    def sync(self, key=None):
        """Hook for syncing DB

        If not applicable, add a sync method with just 'pass'.
        """
        raise NotImplementedError

    def migrate_to(self, other_db):
        assert self._is_open
        assert isinstance(other_db, BaseDatabase)
        assert other_db._is_open
        for key in self._schema.keys():
            setattr(other_db, key, getattr(self, key))


class ShelveDatabase(BaseDatabase):
    """Wrapper for typed `shelve` DB storing TwitterHAL data."""

    def __init__(self, db_path="twitterhal"):
        """Initialize the DB.

        Args:
            db_path (str, optional): Path to the .db file on disk, without
                extension. Default: "twitterhal"
        """
        super().__init__()
        self._db_path = db_path
        self._lock = RLock()

    def add_key(self, name, type_, **defaults):
        assert not self._is_open, "Cannot add to schema once DB has been opened"
        super().add_key(name, type_, **defaults)

    def setattr(self, name, value):
        with self._lock:
            self._db[name] = value

    def open(self):
        with self._lock:
            self._db = shelve.open(self._db_path)
            for k, v in self._schema.items():
                setattr(self, k, self._db.get(k, v.type(**v.defaults)))
            self._is_open = True

    def close(self):
        with self._lock:
            self.sync()
            self._db.close()
        super().close()

    def sync(self, key=None):
        with self._lock:
            for k in self._schema.keys():
                if key is None or k == key:
                    self._db[k] = getattr(self, k)
            self._db.sync()


class RedisDatabase(BaseDatabase):
    def __init__(self, **kwargs):
        """Initialize Redis DB

        Args:
            **kwargs (optional): All these will be sent to redis.Redis(). See
                https://github.com/andymccurdy/redis-py for more info.
        """
        super().__init__()
        self._redis_kwargs = kwargs

    def __setattr__(self, name, value):
        if not name.startswith("_") and self._is_open:
            if isinstance(value, list):
                value = RedisList(self._redis, name, value)
            elif isinstance(value, UserList) and not hasattr(value, "_redis_wrapped"):
                value = RedisList.wrap(value, self._redis, name, overwrite=True)
        super().__setattr__(name, value)

    def add_key(self, name, type_, **defaults):
        if issubclass(type_, list):
            type_ = RedisList
        super().add_key(name, type_, **defaults)

    def setattr(self, name, value):
        if not isinstance(value, (list, UserList)):
            self._redis[name] = pickle.dumps(value, protocol=settings.PICKLE_PROTOCOL)

    def close(self):
        self.sync()
        self._redis.close()
        super().close()

    def open(self):
        from redis import Redis

        # Quick check so the number of databases is sufficient
        if "db" in self._redis_kwargs and self._redis_kwargs["db"] > 0:
            redis_kwargs = self._redis_kwargs.copy()
            redis_kwargs["db"] = 0
            redis = Redis(**redis_kwargs)
            dbs = redis.config_get("databases")
            assert int(dbs["databases"]) > self._redis_kwargs["db"], \
                f"Tried to open Redis DB #{self._redis_kwargs['db']}, but there are only {dbs['databases']} databases"
            redis.close()

        self._redis = Redis(**self._redis_kwargs)
        for key, item in self._schema.items():
            if item.type is RedisList or issubclass(item.type, list):
                setattr(self, key, RedisList(self._redis, key, **item.defaults))
            elif issubclass(item.type, UserList):
                setattr(self, key, RedisList.wrap(item.type(**item.defaults), self._redis, key))
            else:
                value = self._redis.get(key)
                if value is None:
                    value = item.type(**item.defaults)
                else:
                    value = pickle.loads(value)
                setattr(self, key, value)
        self._is_open = True

    def sync(self, key=None):
        from redis import ResponseError
        for k, item in self._schema.items():
            if key is not None and k != key:
                continue
            if item.type is RedisList:
                getattr(self, k).sync()
            elif issubclass(item.type, UserList):
                userlist = getattr(self, k)
                if not isinstance(userlist.data, RedisList):
                    # If done right, this shouldn't happen. But anyway ...
                    userlist = RedisList.wrap(userlist, self._redis, k, overwrite=True)
                userlist.data.sync()
        # Fail silently if another save is already in progress
        try:
            self._redis.bgsave()
        except ResponseError:
            pass


class RedisList(UserList):
    def __init__(self, redis, key, initlist=None):
        """A near-complete UserList implementation of Redis lists.

        Tries to mimick a Python list as closely as possible, in the most
        optimized way. However, methods that would return a _new_ list instance
        (.copy, __add__, etc) will not return a RedisList instance,
        since that would require a new Redis key, but instead a regular list.

        This class has kind of dual use cases, depending on what sort of list
        we are dealing with. For ordinary Python list objects, just replace
        them with a RedisList instance. For other UserList objects, however,
        the preferred method is to transparently "wrap" them with
        RedisList.wrap(), which replaces their `data` attribute but otherwise
        leaves them intact.

        Design goal: Data retrieval only touches self.cache, data update
        changes Redis list first and then updates self.cache accordingly.

        Args:
            redis (redis.Redis): A Redis instance
            key (str): Redis DB key to use
            initlist (Sequence, optional): Initial data. NB: This will
                overwrite any pre-existing Redis list. If this is not what you
                want, initialize with initlist=None and then append your new
                data.
        """
        self.redis = redis
        self.key = key
        self._redis_wrapped = True
        if initlist is not None:
            if isinstance(initlist, UserList):
                self.data = initlist.data[:]
            else:
                self.data = list(initlist)
        else:
            self.push_to_cache()

    @classmethod
    def wrap(cls, userlist, redis, key, overwrite=False):
        """Wrap the underlying list of a UserList

        This will make RedisList act as a transparent "backend" for a UserList
        object, by setting its `data` attribute to a new RedisList.

        Args:
            userlist (collections.UserList)
            redis (redis.Redis)
            key (str): This will be used as key for the Redis DB
            overwrite (bool, optional): If True, will overwrite any
                pre-existing contents for this key in the Redis DB with the
                contents of userlist.data. If False, the contents of
                userlist.data will be disregarded and no longer available.
                Default: False.

        Returns:
            The same UserList, but now "wrapped".
        """
        assert isinstance(userlist, UserList)
        userlist.data = cls(redis, key, initlist=userlist.data if overwrite else None)
        userlist._redis_wrapped = True
        return userlist

    def push_to_cache(self):
        self.cache = [pickle.loads(i) for i in self.redis.lrange(self.key, 0, -1)]

    def sync(self):
        self.data = self.cache

    @property
    def data(self):
        return self.cache

    @data.setter
    def data(self, value):
        if value != self.cache:
            def set_data(pipe):
                pipe.multi()
                pipe.delete(self.key)
                pipe.rpush(self.key, *[pickle.dumps(i, protocol=settings.PICKLE_PROTOCOL) for i in value])
            self.cache = value
            if value:
                self.redis.transaction(set_data, self.key)

    def __setitem__(self, i, item):
        from redis import ResponseError
        try:
            self.redis.lset(self.key, i, pickle.dumps(item, protocol=settings.PICKLE_PROTOCOL))
        except ResponseError:
            raise IndexError("list assignment index out of range")
        else:
            self.cache[i] = item

    def __delitem__(self, i):
        try:
            self.pop(i)
        except IndexError:
            raise IndexError("list assignment index out of range")
        else:
            del self.cache[i]

    def __iter__(self):
        return self.cache.__iter__()

    def __iadd__(self, other):
        self.extend(other)
        return self

    def __imul__(self, n):
        if not isinstance(n, int):
            raise TypeError(f"can't multiply sequence by non-int of type '{n.__class__.__name__}'")
        if n < 0:
            n = 0
        if n == 0:
            self.clear()
        elif n > 1:
            items = self.redis.lrange(self.key, 0, -1)
            if items:
                def multiply(pipe):
                    pipe.multi()
                    for _ in range(1, n):
                        pipe.rpush(self.key, *items)
                self.redis.transaction(multiply, self.key)
                self.push_to_cache()
        return self

    def append(self, item):
        self.redis.rpush(self.key, pickle.dumps(item, protocol=settings.PICKLE_PROTOCOL))
        self.cache.append(item)

    def insert(self, i, item):
        ref_item = self.redis.lindex(self.key, i)
        if ref_item is None:
            # Mimicking Python's list insert behaviour
            if i >= 0:
                self.append(item)
            else:
                self.redis.lpush(self.key, pickle.dumps(item, protocol=settings.PICKLE_PROTOCOL))
        else:
            self.redis.linsert(self.key, "BEFORE", ref_item, pickle.dumps(item, protocol=settings.PICKLE_PROTOCOL))
        self.cache.insert(i, item)

    def pop(self, i=-1):
        if self.redis.llen(self.key) == 0:
            raise IndexError("pop from empty list")
        if i == -1:
            value = self.redis.rpop(self.key)
        elif i == 0:
            value = self.redis.lpop(self.key)
        else:
            value = self.redis.lindex(self.key, i)
            if value is None:
                raise IndexError("pop index out of range")
            self.redis.lrem(self.key, 1, value)
        return self.cache.pop(i)

    def remove(self, item):
        try:
            index = self.cache.index(item)
        except ValueError:
            raise ValueError("list.remove(x): x not in list")
        self.pop(index)

    def clear(self):
        del self.redis[self.key]
        self.cache = []

    def extend(self, other):
        if isinstance(other, UserList) and other.data:
            other = other.data.copy()
        if other:
            # Will throw TypeError if `other` is not iterable:
            self.redis.rpush(self.key, *[pickle.dumps(i, protocol=settings.PICKLE_PROTOCOL) for i in other])
            self.cache.extend(other)

    # The following methods do not return a RedisList instance, as that
    # would require a new Redis key. Instead, they return an instance of the
    # underlying sequence type (self.list_type).
    def copy(self):
        return self.data.copy()

    def __add__(self, other):
        return list(self.data + other)

    def __radd__(self, other):
        return list(list(other) + self.data)

    def __mul__(self, n):
        return list(self.data * n)
    __rmul__ = __mul__


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
        """Make a Tweet object out of a twitter.models.Status object

        Will set .text to .full_text if available, and then .filtered_text to
        strip_phrase(.text)
        """
        kwargs = {}
        for param, default in status.param_defaults.items():
            kwargs[param] = getattr(status, param, default)
        return cls(**kwargs)


class TweetList(UserList):
    """A list of Tweet objects."""

    def __init__(self, initlist=None, unique=False):
        """Initialize the list.

        Args:
            initlist (Sequence, optional): A sequence of Tweet objects
            unique (bool, optional): If True, the list will only contain
                unique Tweets, based on status ID. (Yes, I could use a set for
                that, but I want to be able to use the same structure for
                different kinds of Tweet lists)
        """
        self.unique = unique
        self._data = []
        if initlist is not None:
            self.data = initlist

    @property
    def data(self):
        return self._data

    @data.setter
    def data(self, value):
        if self.unique and len(value) > 0:
            tmplist = []
            for t in value:
                if t not in tmplist:
                    tmplist.append(t)
            if isinstance(value, UserList):
                value.data = tmplist
                self._data = value
            else:
                self._data = tmplist
        else:
            self._data = value

    def __setitem__(self, i, item):
        if not self.unique or item not in self.data or self.data.index(item) == i:
            self.data[i] = item

    def __add__(self, other):
        if isinstance(other, UserList):
            other = other.data
        if self.unique:
            return self.__class__(self.data + [t for t in other if t not in self.data], unique=True)
        return self.__class__(self.data + other)

    def __radd__(self, other):
        if isinstance(other, UserList):
            if isinstance(other, self.__class__):
                unique = other.unique
            else:
                unique = False
            other = other.data
        if unique:
            return self.__class__(other + [t for t in self.data if t not in other], unique=True)
        return self.__class__(other + self.data)

    def __iadd__(self, other):
        if isinstance(other, UserList):
            other = other.data
        if self.unique:
            self.data += [t for t in other if t not in self.data]
        else:
            self.data += other
        return self

    def append(self, item):
        if not self.unique or item not in self.data:
            self.data.append(item)

    def insert(self, i, item):
        if not self.unique or item not in self.data:
            self.data.insert(i, item)

    def extend(self, other):
        if isinstance(other, UserList):
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
        return self.__class__(result, unique=self.unique)

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
        data = self.data.copy()
        old_count = len(data)
        self.data.clear()
        self.data.extend([tweet for tweet in data if tweet.created_at_in_seconds >= t])
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
        return self.__class__([t for t in self.data if ratio(t.filtered_text, string) > 0.8], unique=self.unique)

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
