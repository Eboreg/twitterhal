from collections import UserList
from datetime import datetime
from shelve import DbfilenameShelf
from threading import RLock
from typing import Any, Dict, Iterable, List, Optional, Type, TypeVar, Union

from twitter.models import Status


T = TypeVar("T")


class DatabaseItem:
    def __init__(self, name: str, type_: Type[T], default_value: T):
        ...

    def __setattr__(self, name: str, value: T):
        ...


class Database:
    __writeback: bool
    __keep_synced: bool
    __is_open: bool
    __db_name: str
    __lock: RLock
    __db: DbfilenameShelf
    __schema: Dict[str, DatabaseItem]

    def __init__(self, db_name: str, writeback: bool, keep_synced: bool):
        ...

    def add_key(self, name: str, type_: Type[T], default: T):
        ...


class Tweet(Status):
    created_at: Optional[str]
    filtered_text: str
    full_text: Optional[str]
    id: Optional[int]
    in_reply_to_status_id: Optional[int]
    is_answered: bool
    is_processed: bool
    text: str

    def __init__(self, is_answered: bool, is_processed: bool, filtered_text: Optional[str], **kwargs):
        ...

    def __eq__(self, other: Any) -> bool:
        ...

    def __setattr__(self, name: str, value: Any):
        ...

    @classmethod
    def from_status(cls, status: Status):
        ...


class TweetList(UserList, Iterable[Tweet]):
    data: List[Tweet]
    unique: bool
    earliest_ts: int
    latest_ts: int
    earliest_date: Optional[datetime]
    latest_date: Optional[datetime]
    processed: TweetList
    non_processed: TweetList
    answered: TweetList
    unanswered: TweetList
    original_posts: TweetList
    replies: TweetList

    def __init__(self, initlist: Optional[List[Tweet]], unique: bool):
        ...

    def get_by_id(self, id: int) -> Optional[Tweet]:
        ...

    def only_in_language(self, language_code: str) -> TweetList:
        ...

    def older_than(self, t: Union[float, int, datetime]) -> TweetList:
        ...

    def remove_older_than(self, t: Union[float, int, datetime]) -> int:
        ...

    def fuzzy_duplicates(self, item: Union[str, Tweet, Status]) -> TweetList:
        ...
