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
    def __init__(self, name, type_, default_value):
        self.type = type_
        self.name = name
        self.default_value = self.value = default_value

    def __setattr__(self, name, value):
        if name == "value" and not isinstance(value, self.type):
            raise TypeError("%s is of wrong type for %s, should be: %s" % (value, self.name, self.type))
        super().__setattr__(name, value)


class Database:
    """Wrapper for typed `shelve` DB storing TwitterHAL data."""

    def __init__(self, db_path="twitterhal"):
        """Initialize the DB.

        Args:
            db_path (str, optional): Path to the .db file on disk, without
                extension. Default: "twitterhal"
        """
        self.__is_open = False
        self.__db_path = db_path
        self.__lock = RLock()
        self.__schema = {
            "posted_tweets": DatabaseItem("posted_tweets", TweetList, TweetList(unique=True)),
            "mentions": DatabaseItem("mentions", TweetList, TweetList(unique=True)),
        }

    def add_key(self, name, type_, default):
        assert not self.__is_open, "Cannot add to schema once DB has been opened"
        self.__schema[name] = DatabaseItem(name, type_, default)

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *args, **kwargs):
        self.close()

    def __setattr__(self, name, value):
        if not name.startswith("_") and self.__is_open:
            with self.__lock:
                assert name in self.__schema, "Key %s not present in DB schema" % name
                self.__schema[name].value = value
                self.__db[name] = value
        super().__setattr__(name, value)

    def open(self):
        with self.__lock:
            self.__db = shelve.open(self.__db_path)
            for k, v in self.__schema.items():
                setattr(self, k, self.__db.get(k, v.value))
            self.__is_open = True

    def close(self):
        with self.__lock:
            self.sync()
            self.__db.close()
            self.__is_open = False

    def sync(self):
        with self.__lock:
            for key in self.__schema.keys():
                self.__db[key] = getattr(self, key)
            self.__db.sync()


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
