import pickle
import shelve
from collections import UserList
from threading import RLock


class DatabaseItem:
    def __init__(self, type_, default=None, **default_kwargs):
        self.type = type_
        self.default = default
        self.default_kwargs = default_kwargs

    def get_default(self):
        if self.default is None:
            return self.type(**self.default_kwargs)
        return self.default


class BaseDatabase:
    def __init__(self):
        """Initialize the DB."""
        self._is_open = False
        self._schema = {}

    def add_key(self, name, type_, default=None, **default_kwargs):
        """Add new key to database

        Args:
            name (str): Name of the key. The value will be available as
                self.`name` on this object.
            type_ (type): Type of object stored under this key
        """
        self._schema[name] = DatabaseItem(type_, default=default, **default_kwargs)

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *args, **kwargs):
        self.close()

    def __setattr__(self, name, value):
        if not name.startswith("_"):
            assert name in self._schema, "Key %s not present in DB schema" % name
            assert isinstance(value, self._schema[name].type), \
                f"'{name}' is of wrong type '{value.__class__.__name__}', " \
                f"should be: '{self._schema[name].type.__name__}'"
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

    def add_key(self, name, type_, default=None, **default_kwargs):
        assert not self._is_open, "Cannot add to schema once DB has been opened"
        super().add_key(name, type_, default=default, **default_kwargs)

    def setattr(self, name, value):
        with self._lock:
            self._db[name] = value

    def open(self):
        with self._lock:
            self._db = shelve.open(self._db_path)
            for k, v in self._schema.items():
                setattr(self, k, self._db.get(k, v.default or v.type(**v.default_kwargs)))
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
    def __init__(self, pickle_protocol=pickle.DEFAULT_PROTOCOL, namespace=None, **kwargs):
        """Initialize Redis DB

        Args:
            **kwargs (optional): All these will be sent to redis.Redis(). See
                https://github.com/andymccurdy/redis-py for more info.
        """
        from redis import Redis

        super().__init__()
        self._pickle_protocol = pickle_protocol
        self._namespace = namespace

        # Quick check so the number of databases is sufficient
        if "db" in kwargs and kwargs["db"] > 0:
            redis_kwargs = kwargs.copy()
            redis_kwargs["db"] = 0
            redis = Redis(**redis_kwargs)
            dbs = redis.config_get("databases")
            if int(dbs["databases"]) <= kwargs["db"]:
                redis.close()
                raise ValueError(
                    f"Tried to open Redis DB #{kwargs['db']}, but there are only {dbs['databases']} databases")
            redis.close()

        self._redis = Redis(**kwargs)

    def __setattr__(self, name, value):
        if not name.startswith("_") and self._is_open:
            if isinstance(value, (UserList, list)) and not hasattr(value, "_redis_wrapped"):
                value = RedisList.wrap(
                    value,
                    self._redis,
                    self.get_redis_key(name),
                    overwrite=True,
                    pickle_protocol=self._pickle_protocol
                )
        super().__setattr__(name, value)

    def add_key(self, name, type_, default=None, **default_kwargs):
        if issubclass(type_, list):
            if default is None:
                initlist = type_()
            else:
                initlist = type_(default.copy())
            default = None
            type_ = RedisList
            default_kwargs.update({
                "initlist": initlist,
                "redis": self._redis,
                "key": self.get_redis_key(name),
                "pickle_protocol": self._pickle_protocol
            })
        super().add_key(name, type_, default=default, **default_kwargs)

    def get_redis_key(self, name):
        return f"{self._namespace}:{name}" if self._namespace else name

    def setattr(self, name, value):
        if not isinstance(value, (list, UserList)):
            self._redis[self.get_redis_key(name)] = pickle.dumps(value, protocol=self._pickle_protocol)

    def close(self):
        self.sync()
        self._redis.close()
        super().close()

    def open(self):
        for key, item in self._schema.items():
            if item.type is RedisList:
                setattr(self, key, item.get_default())
            elif issubclass(item.type, UserList):
                unique = item.default_kwargs.get("unique", False)
                setattr(self, key, RedisList.wrap(
                    item.get_default(),
                    self._redis,
                    self.get_redis_key(key),
                    unique=unique,
                    pickle_protocol=self._pickle_protocol
                ))
            else:
                value = self._redis.get(self.get_redis_key(key))
                setattr(self, key, item.get_default() if value is None else pickle.loads(value))
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
                    userlist = RedisList.wrap(userlist, self._redis, self.get_redis_key(k), overwrite=True)
                userlist.data.sync()
            else:
                self._redis.set(self.get_redis_key(k), pickle.dumps(getattr(self, k), protocol=self._pickle_protocol))
        # Fail silently if another save is already in progress
        try:
            self._redis.bgsave()
        except ResponseError:
            pass


class RedisList(UserList):
    def __init__(self, redis, key, initlist=[], overwrite=False, pickle_protocol=pickle.DEFAULT_PROTOCOL):
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
            initlist (Sequence, optional): Initial data; see comments for
                `overwrite`.
            overwrite (bool, optional): If True, will overwrite any
                pre-existing contents for this key in the Redis DB with the
                contents of `initlist`. If False, the contents of `initlist`
                will be disregarded and no longer available. Default: False.
        """
        self.redis = redis
        self.key = key
        self.pickle_protocol = pickle_protocol
        self._redis_wrapped = True
        self.list_type = type(initlist)
        if overwrite:
            if isinstance(initlist, UserList):
                self.data = initlist.data[:]
            else:
                self.data = initlist
        else:
            self.push_to_cache()

    def __getattr__(self, name):
        # This hack enables us to transparently access custom attributes and
        # methods on underlying lists that extend `list`.
        return getattr(self.data, name)

    @classmethod
    def wrap(cls, userlist, redis, key, overwrite=False, unique=False, pickle_protocol=pickle.DEFAULT_PROTOCOL):
        """Wrap an existing list

        This will make RedisList act as a transparent "backend" for a UserList
        object. by setting its `data` attribute to a new RedisList.

        Args:
            userlist (collections.UserList)
            redis (redis.Redis)
            key (str): This will be used as key for the Redis DB
            overwrite (bool, optional): If True, will overwrite any
                pre-existing contents for this key in the Redis DB with the
                contents of userlist.data. If False, the contents of
                userlist.data will be disregarded and no longer available.
                Default: False.
            unique (bool, optional): If True, and `overwrite` is False, will
                make sure data only contains unique items (going by their
                __hash__() value).

        Returns:
            "Wrapped" UserList
        """
        assert isinstance(userlist, UserList)
        initlist = userlist.data
        userlist.data = cls(redis, key, initlist=initlist, overwrite=overwrite, pickle_protocol=pickle_protocol)
        if unique and not overwrite:
            userlist.data.data = list(set(userlist.data.data))
        userlist._redis_wrapped = True
        return userlist

    def push_to_cache(self):
        self.cache = self.list_type([pickle.loads(i) for i in self.redis.lrange(self.key, 0, -1)])

    def sync(self):
        self.data = self.cache

    @property  # type: ignore
    def data(self):
        return self.cache

    @data.setter
    def data(self, value):
        def set_data(pipe):
            pipe.multi()
            pipe.delete(self.key)
            pipe.rpush(self.key, *[pickle.dumps(i, protocol=self.pickle_protocol) for i in value])
        self.cache = self.list_type(value)
        if value:
            self.redis.transaction(set_data, self.key)

    def __setitem__(self, i, item):
        from redis import ResponseError
        try:
            self.redis.lset(self.key, i, pickle.dumps(item, protocol=self.pickle_protocol))
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
        self.redis.rpush(self.key, pickle.dumps(item, protocol=self.pickle_protocol))
        self.cache.append(item)

    def insert(self, i, item):
        ref_item = self.redis.lindex(self.key, i)
        if ref_item is None:
            # Mimicking Python's list insert behaviour
            if i >= 0:
                self.append(item)
            else:
                self.redis.lpush(self.key, pickle.dumps(item, protocol=self.pickle_protocol))
        else:
            self.redis.linsert(self.key, "BEFORE", ref_item, pickle.dumps(item, protocol=self.pickle_protocol))
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
            self.redis.rpush(self.key, *[pickle.dumps(i, protocol=self.pickle_protocol) for i in other])
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
