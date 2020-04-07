import shelve
from collections import UserList
from datetime import datetime
from email.utils import formatdate
from typing import TYPE_CHECKING, Iterable

from Levenshtein import ratio  # pylint: disable=no-name-in-module
from twitter.models import Status

from twitterhal.util import strip_phrase

if TYPE_CHECKING:
    from shelve import DbfilenameShelf
    from typing import Any, List, Optional, Type, TypeVar, Union
    T = TypeVar("T")


class DatabaseItem:
    def __init__(self, name: str, type_: "Type[T]", default_value: "T"):
        self.type = type_
        self.name = name
        self.default_value = self.value = default_value

    def __setattr__(self, name, value):
        if name == "value" and not isinstance(value, self.type):
            raise TypeError("%s is of wrong type for %s, should be: %s" % (value, self.name, self.type))
        super().__setattr__(name, value)


class Database:
    """Wrapper for typed `shelve` DB storing TwitterHAL data."""
    def __init__(self, db_name: str = "twitterhal", writeback: bool = False, keep_synced: bool = True, **extra_keys):
        """Initialize the DB.

        Args:
            db_name (str, optional): Name of the .db file on disk, without
                extension. Default: "twitterhal"
            writeback (bool, optional): Whether to open the shelve with
                writeback, see https://docs.python.org/3.7/library/shelve.html.
                Default: False
            keep_synced (bool, optional): If True, will sync the DB to disk
                every time a value is altered. May slow things down with large
                databases. Default: True
            **extra_keys: DB will contain these keys, with their values as
                defaults
        """
        self.__writeback = writeback
        self.__keep_synced = keep_synced
        self.__is_open = False
        self.__db_name = db_name
        self.__db: "DbfilenameShelf"
        self.__schema = {
            "posted_tweets": DatabaseItem("posted_tweets", TweetList, TweetList(unique=True)),
            "mentions": DatabaseItem("mentions", TweetList, TweetList(unique=True)),
            "api_requests": DatabaseItem("api_requests", dict, {}),
        }
        for k, v in extra_keys.values():
            self.__schema[k] = DatabaseItem(k, type(v), v)

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *args, **kwargs):
        self.close()

    def __setattr__(self, name: str, value):
        if not name.startswith("__"):
            if not self.__is_open:
                raise AttributeError("Database is not open; run open() first")
            elif name not in self.__schema:
                raise AttributeError("Key %s not present in DB schema" % name)
            else:
                self.__schema[name].value = value
                self.__db[name] = value
                if self.__keep_synced:
                    self.__db.sync()
        super().__setattr__(name, value)

    def open(self):
        self.__db = shelve.open(self.__db_name, writeback=self.__writeback)
        for k, v in self.__schema.items():
            setattr(self, k, self.__db.get(k, v.value))
        self.__is_open = True

    def close(self):
        self.__db.close()
        self.__is_open = False


class Tweet(Status):
    """Extended version of Status from the `twitter` package.

    Not dependent on whether we run 'extended mode' or not; self.text will
    contain status.full_text if available, otherwise status.text.

    self.filtered_text: tweet text filtered by utils.strip_phrase()

    self.is_* are boolean flags usable for different categories of tweets:
    self.is_answered - tweet that mentions us, to denote whether it's been
        answered
    self.is_processed - incoming tweet, to denote whether it's been processed
        and learnt by MegaHAL
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
        self,
        is_answered: bool = False,
        is_processed: bool = False,
        filtered_text: "Optional[str]" = None,
        **kwargs
    ):
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
    """A list of Tweet objects."""

    data: "List[Tweet]"
    unique: bool = False

    def __init__(self, initlist: "Optional[List[Tweet]]" = None, unique: bool = False):
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

    def get_by_id(self, id: int) -> "Optional[Tweet]":
        if not self.unique:
            raise ValueError("Refusing to run get_by_id() when unique == False")
        try:
            return [t for t in self.data if t.id == id][0]
        except IndexError:
            return None

    def only_in_language(self, language_code: str):
        """Get TweetList of those Tweets that seem to be in a given language.

        Tweet language is decided by the `detectlanguage` API:
        https://detectlanguage.com/

        Requires that detectlanguage.configuration.api_key has been set.
        """
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
        """Get TweetList of Tweets older than a given value.

        Args:
            t (float, int, datetime): Get all that are older than this; float
                or int is interpreted as UNIX timestamps.
        """
        if isinstance(t, datetime):
            t = t.timestamp()
        if not isinstance(t, (int, float)):
            raise ValueError("Argument must be a timestamp or datetime")
        return self.__class__([tweet for tweet in self.data if tweet.created_at_in_seconds < t])

    def remove_older_than(self, t: "Union[float, int, datetime]") -> int:
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

    def fuzzy_duplicates(self, item: "Union[str, Tweet, Status]") -> "TweetList":
        """Return TweetList of Tweets whose text is sufficiently similar to
        `item` (Levenshtein ratio > 0.8)
        """
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
    def processed(self) -> "TweetList":
        """Return TweetList of all Tweets that are flagged as processed"""
        return self.__class__([t for t in self.data if t.is_processed], unique=self.unique)

    @property
    def non_processed(self) -> "TweetList":
        """Return TweetList of all Tweets that are NOT flagged as processed"""
        return self.__class__([t for t in self.data if not t.is_processed], unique=self.unique)

    @property
    def answered(self) -> "TweetList":
        """Return TweetList of all Tweets that are flagged as replied"""
        return self.__class__([t for t in self.data if t.is_answered], unique=self.unique)

    @property
    def unanswered(self) -> "TweetList":
        """Return TweetList of all Tweets that are NOT flagged as replied"""
        return self.__class__([t for t in self.data if not t.is_answered], unique=self.unique)

    @property
    def original_posts(self) -> "TweetList":
        """Return TweetList of all Tweets that are original posts, i.e. NOT
        replies to another tweet
        """
        return self.__class__([t for t in self.data if t.in_reply_to_status_id is None], unique=self.unique)

    @property
    def replies(self) -> "TweetList":
        """Return TweetList of all Tweets that are replies to another tweet"""
        return self.__class__([t for t in self.data if t.in_reply_to_status_id is not None], unique=self.unique)
