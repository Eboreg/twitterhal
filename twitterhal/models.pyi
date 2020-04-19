from collections import UserList
from datetime import datetime
from shelve import DbfilenameShelf
from threading import RLock
from typing import Any, Dict, Iterable, List, Optional, Type, TypeVar, Union

from twitter.models import Status


T = TypeVar("T")


class DatabaseItem:
    def __init__(self, name: str, type_: Type[T], default_value: T): ...
    def __setattr__(self, name: str, value: T): ...


class Database:
    __db_name: str
    __db: DbfilenameShelf
    __is_open: bool
    __lock: RLock
    __schema: Dict[str, DatabaseItem]

    def __init__(self, db_name: str): ...
    def add_key(self, name: str, type_: Type[T], default: T): ...
    def close(self): ...
    def open(self): ...
    def sync(self): ...


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
    def __init__(self, is_answered: bool, is_processed: bool, filtered_text: Optional[str], **kwargs): ...
    def __setattr__(self, name: str, value: Any): ...
    @classmethod
    def from_status(cls, status: Status) -> "Tweet": ...


class TweetList(UserList, Iterable[Tweet]):
    answered: TweetList
    data: List[Tweet]
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

    def __init__(self, initlist: Optional[List[Tweet]], unique: bool): ...
    def fuzzy_duplicates(self, item: Union[str, Tweet, Status]) -> TweetList: ...
    def get_by_id(self, id: int) -> Optional[Tweet]: ...
    def only_in_language(self, language_code: str) -> TweetList: ...
    def remove_older_than(self, t: Union[float, int, datetime]) -> int: ...
