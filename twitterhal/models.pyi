from collections import UserList
from datetime import datetime
from shelve import DbfilenameShelf
from threading import RLock
from typing import (
    Any, Dict, Generic, Iterable, List, Optional, Type, TypeVar, Union,
)

from redis import Redis
from twitter.models import Status


DBI = TypeVar("DBI")


class DatabaseItem(Generic[DBI]):
    type: Type[DBI]
    defaults: Dict[str, Any]

    def __init__(self, type_: Type[DBI], **defaults): ...


class BaseDatabase:
    _is_open: bool
    _schema: Dict[str, DatabaseItem]

    def __enter__(self) -> BaseDatabase: ...
    def __exit__(self, *args, **kwargs): ...
    def __init__(self): ...
    def __setattr__(self, name: str, value: Any): ...
    def add_key(self, name: str, type_: Type[DBI], **defaults): ...
    def close(self): ...
    def migrate_to(self, other_db: BaseDatabase): ...
    def open(self): ...
    def setattr(self, name: str, value: Any): ...
    def sync(self, key: Optional[str]): ...


class ShelveDatabase(BaseDatabase):
    _db_path: str
    _db: DbfilenameShelf
    _lock: RLock

    def __init__(self, db_path: str): ...


class RedisDatabase(BaseDatabase):
    _redis: Redis
    _redis_kwargs: Dict[str, Any]

    def __init__(self, **kwargs): ...


class RedisList(UserList):
    redis: Redis
    key: str
    data: list
    cache: list

    def __init__(self, redis: Redis, key: str, initlist: Union[List, UserList, None]): ...
    def push_to_cache(self): ...
    def sync(self): ...
    @classmethod
    def wrap(cls, userlist: UserList, redis: Redis, key: str, overwrite: bool, unique: bool) -> UserList: ...


class Tweet(Status):
    created_at: Optional[str]
    filtered_text: str
    full_text: Optional[str]
    id: Optional[int]
    in_reply_to_status_id: Optional[int]
    is_answered: bool
    is_processed: bool
    text: str

    def __eq__(self, other: Any) -> bool: ...
    def __hash__(self) -> int: ...
    def __init__(self, is_answered: bool, is_processed: bool, filtered_text: Optional[str], **kwargs): ...
    def __setattr__(self, name: str, value: Any): ...
    @classmethod
    def from_status(cls, status: Status) -> "Tweet": ...


class TweetList(UserList, Iterable[Tweet]):
    answered: TweetList
    data: Union[List[Tweet], UserList[Tweet]]  # type: ignore
    earliest_date: Optional[datetime]
    earliest_ts: int
    latest_date: Optional[datetime]
    latest_ts: int
    non_processed: TweetList
    original_posts: TweetList
    processed: TweetList
    replies: TweetList
    unanswered: TweetList
    unique: bool

    def __init__(self, initlist: Union[List[Tweet], UserList[Tweet], None], unique: bool): ...
    def fuzzy_duplicates(self, item: Union[str, Tweet, Status]) -> TweetList: ...
    def get_by_id(self, id: int) -> Optional[Tweet]: ...
    def only_in_language(self, language_code: str) -> TweetList: ...
    def remove_older_than(self, t: Union[float, int, datetime]) -> int: ...
