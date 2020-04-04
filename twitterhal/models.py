from collections import UserList
from datetime import datetime
from email.utils import formatdate
from typing import Iterable, TYPE_CHECKING

from Levenshtein import ratio  # pylint: disable=no-name-in-module
from twitter.models import Status

from twitterhal.util import strip_phrase

if TYPE_CHECKING:
    from typing import Any, List, Optional, Union


class Tweet(Status):
    """
    `filtered_text` - self.full_text or self.text filtered by strip_phrase()

    `is_*` are flags usable for different categories of tweets:
    `is_answered` - tweets that mention us
    `is_processed` - incoming tweets, to denote whether they have been
    processed and learnt by MegaHAL
    """
    created_at: "Optional[str]"
    filtered_text: str
    full_text: "Optional[str]"
    id: "Optional[int]"
    in_reply_to_status_id: "Optional[int]"
    is_answered: bool
    is_processed: bool
    text: str

    def __init__(
            self, is_answered: bool = False, is_processed: bool = False,
            filtered_text: "Optional[str]" = None, **kwargs):
        super().__init__(**kwargs)
        self.text = self.full_text or self.text
        if filtered_text is None:
            self.filtered_text = strip_phrase(self.text or "")
        else:
            self.filtered_text = filtered_text
        self.is_answered = is_answered
        self.is_processed = is_processed
        self.created_at = self.created_at or formatdate()

    def __eq__(self, other: "Any") -> bool:
        if issubclass(other.__class__, Status):
            return self.id == other.id
        return False

    @classmethod
    def from_status(cls, status: "Status"):
        kwargs = {}
        for param, default in status.param_defaults.items():
            kwargs[param] = getattr(status, param, default)
        return cls(**kwargs)


class TweetList(UserList, Iterable[Tweet]):
    data: "List[Tweet]"
    unique: bool = False

    def __init__(self, initlist: "Optional[List[Tweet]]" = None, unique: bool = False):
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

    def get_by_id(self, id: int) -> "Optional[Tweet]":
        if not self.unique:
            raise ValueError("Refusing to run get_by_id() when unique == False")
        try:
            return [t for t in self.data if t.id == id][0]
        except IndexError:
            return None

    def only_in_language(self, language_code: str):
        import detectlanguage
        if detectlanguage.configuration.api_key is None:
            raise ValueError("Detectlanguage API key not set")
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

    def older_than(self, t: "Union[float, int, datetime]") -> "TweetList":
        if isinstance(t, datetime):
            t = t.timestamp()
        if not isinstance(t, (int, float)):
            raise ValueError("Argument must be a timestamp or datetime")
        return self.__class__([tweet for tweet in self.data if tweet.created_at_in_seconds < t])

    def remove_older_than(self, t: "Union[float, int, datetime]") -> int:
        # Returns number of items removed
        if isinstance(t, datetime):
            t = t.timestamp()
        if not isinstance(t, (int, float)):
            raise ValueError("Argument must be a timestamp or datetime")
        old_count = len(self.data)
        self.data = [tweet for tweet in self.data if tweet.created_at_in_seconds >= t]
        return old_count - len(self.data)

    def fuzzy_duplicates(self, item: "Union[str, Tweet, Status]") -> "TweetList":
        if isinstance(item, Tweet):
            string = item.filtered_text
        elif isinstance(item, Status):
            string = strip_phrase(item.full_text or item.text)
        elif isinstance(item, str):
            string = strip_phrase(item)
        else:
            raise ValueError("item has to be str, Tweet, or Status")
        return self.__class__([t for t in self.data if ratio(t.filtered_text, string) > 0.8])

    @property
    def earliest_ts(self) -> int:
        return min([t.created_at_in_seconds for t in self.data], default=0)

    @property
    def latest_ts(self) -> int:
        return max([t.created_at_in_seconds for t in self.data], default=0)

    @property
    def earliest_date(self) -> "Optional[datetime]":
        ts = self.earliest_ts
        return datetime.fromtimestamp(ts) if ts > 0 else None

    @property
    def latest_date(self) -> "Optional[datetime]":
        ts = self.latest_ts
        return datetime.fromtimestamp(ts) if ts > 0 else None

    @property
    def non_processed(self) -> "TweetList":
        return self.__class__([t for t in self.data if not t.is_processed], unique=self.unique)

    @property
    def processed(self) -> "TweetList":
        return self.__class__([t for t in self.data if t.is_processed], unique=self.unique)

    @property
    def answered(self) -> "TweetList":
        return self.__class__([t for t in self.data if t.is_answered], unique=self.unique)

    @property
    def unanswered(self) -> "TweetList":
        return self.__class__([t for t in self.data if not t.is_answered], unique=self.unique)

    @property
    def original_posts(self) -> "TweetList":
        return self.__class__([t for t in self.data if t.in_reply_to_status_id is None], unique=self.unique)

    @property
    def replies(self) -> "TweetList":
        return self.__class__([t for t in self.data if t.in_reply_to_status_id is not None], unique=self.unique)
