import shelve
from collections import UserList
from threading import RLock
from typing import Any, Dict, Generic, List, Optional, Type, TypeVar, Union

from redis import Redis


DBI = TypeVar("DBI")


class RedisUserList(UserList):
    data: RedisList  # type: ignore
    _redis_wrapped: bool


class DatabaseItem(Generic[DBI]):
    type: Type[DBI]
    default: Optional[DBI]
    default_kwargs: Dict[str, Any]

    def __init__(self, type_: Type[DBI], default: Optional[DBI], **default_kwargs): ...
    def get_default(self) -> DBI: ...


class BaseDatabase:
    is_open: bool
    _schema: Dict[str, DatabaseItem]

    def __enter__(self) -> BaseDatabase: ...
    def __exit__(self, *args, **kwargs): ...
    def __init__(self): ...
    def __setattr__(self, name: str, value: Any): ...
    def add_key(self, name: str, type_: Type[DBI], default: Optional[DBI], **default_kwargs): ...
    def close(self): ...
    def migrate_to(self, other_db: BaseDatabase): ...
    def open(self): ...
    def setattr(self, name: str, value: Any): ...
    def sync(self, key: Optional[str]): ...


class ShelveDatabase(BaseDatabase):
    _db_path: str
    _db: shelve.DbfilenameShelf
    _lock: RLock

    def __enter__(self) -> ShelveDatabase: ...
    def __init__(self, db_path: str): ...


class RedisDatabase(BaseDatabase):
    _namespace: Optional[str]
    _pickle_protocol: int
    _redis: Redis
    _redis_kwargs: Dict[str, Any]

    def __enter__(self) -> RedisDatabase: ...
    def __init__(self, pickle_protocol: int, namespace: Optional[str], **kwargs): ...
    def get_redis_key(self, name: str) -> str: ...


class RedisList(UserList):
    _redis_wrapped: bool
    cache: List
    data: List
    key: str
    list_type: Type
    pickle_protocol: int
    redis: Redis

    def __getattr__(self, name: str) -> Any: ...
    def __init__(self, redis: Redis, key: str, initlist: Union[List, UserList], overwrite: bool, pickle_protocol: int): ...
    def push_to_cache(self): ...
    def sync(self): ...
    @classmethod
    def wrap(cls, userlist: UserList, redis: Redis, key: str, overwrite: bool, unique: bool, pickle_protocol: int) -> UserList: ...
