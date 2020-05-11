import logging
from collections import UserList
from datetime import datetime
from email.utils import formatdate

from Levenshtein import ratio
from twitter.models import Status

from twitterhal.conf import settings
from twitterhal.util import strip_phrase


logger = logging.getLogger(__name__)


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
        self.param_defaults.update({
            "filtered_text": None,
            "is_answered": None,
            "is_processed": None,
        })
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

    def __hash__(self):
        return hash(str(self.id))

    def __repr__(self):
        if self.user:
            return f"Tweet<id={self.id}, screen_name={self.user.screen_name}, created={self.created_at}, " + \
                f"text={self.text}>"
        else:
            return f"<Tweet(id={self.id}, created={self.created_at}, text={self.text})>"

    def __str__(self):
        return repr(self)

    def extend(self, other):
        """Extend this object with (non-default) attributes from `other`

        Args:
            other (Status or Tweet)
        """
        assert isinstance(other, (Status, Tweet))
        for param, default in other.param_defaults.items():
            if getattr(other, param) != default:
                setattr(self, param, getattr(other, param))

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
        self.data = []
        if initlist is not None:
            if self.unique:
                self.data = list(set(initlist))
            else:
                self.data = initlist
        else:
            self.data = []

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

    def __sizeof__(self):
        return self.data.__sizeof__()

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
