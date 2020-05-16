import datetime
import html
import re
import sys

import emoji
from megahal.util import split_to_sentences


emoji_pattern = emoji.get_emoji_regexp()
url_pattern = re.compile(
    r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+",
    flags=re.IGNORECASE
)
# Tries its best to match hashtags as half-assedly defined by Twitter here:
# https://help.twitter.com/en/using-twitter/replies-not-showing-up-and-hashtag-problems
hashtag_pattern = re.compile(r"(?<!\S)(#(?!\d+(?:\s|$))\w+)")


def strip_phrase(phrase):
    # Strip emojis
    phrase = emoji_pattern.sub("", phrase)
    # Unescape HTML entities
    phrase = html.unescape(phrase)
    # Strip URLs and mentions
    phrase = url_pattern.sub("", phrase)
    phrase = re.sub(r"@\w+", "", phrase)
    # Strip hashtags
    phrase = hashtag_pattern.sub("", phrase)
    # Strip quotation marks
    phrase = re.sub(r"[”\"]", "", phrase)
    # Strip lines, stars & dots
    phrase = re.sub(r"\s*[|•*]\s*", " ", phrase)
    # Remote "RT : ", denoting retweet (it used to be a @handle there before
    # we stripped it above)
    phrase = re.sub(r"^rt : ", "", phrase, flags=re.IGNORECASE)
    # Convert non-space whitespace (\n, \t etc) to period + space
    phrase = re.sub(r"[.!?]*[^\S ]+", ". ", phrase)
    # Strip superfluous whitespace
    phrase = re.sub(r"\s{2,}", " ", phrase)
    # Remove trailing ellipsis + sentence that might have been cut off with it
    try:
        if phrase.strip()[-1] == "…":
            phrase = " ".join(split_to_sentences(phrase)[:-1])
    except IndexError:
        pass
    phrase = phrase.strip()
    # Finish with a period if the sentence is unfinished
    if phrase and phrase[-1] not in ".?!":
        phrase += "."
    return phrase


def parse_time_string_list(string):
    result = []
    times = re.split(r",\s*", string)
    for t in times:
        try:
            result.append(datetime.datetime.strptime(t, "%H:%M:%S").time())
        except ValueError:
            result.append(datetime.datetime.strptime(t, "%H:%M").time())
    return result


def print_r(obj, name="", indent=0):
    name = name or obj.__class__.__name__
    if hasattr(obj, "param_defaults"):
        print(" " * indent + name + ":")
        for k, v in obj.param_defaults.items():
            print_r(getattr(obj, k), k, indent + 2)
    elif isinstance(obj, list):
        print(" " * indent + name + ":")
        for i, v in enumerate(obj):
            print_r(v, i, indent + 2)
    elif isinstance(obj, dict):
        print(" " * indent + name + ":")
        for k, v in obj.items():
            print_r(v, k, indent + 2)
    else:
        print(" " * indent, end="")
        if name:
            print(f"{name}: {obj}")
        else:
            print(obj)


def size_r(obj):
    """Rough approximation of an object's cumulative size in bytes"""
    size = 0
    if hasattr(obj, "param_defaults"):
        for k in obj.param_defaults:
            size += size_r(getattr(obj, k))
    elif isinstance(obj, list):
        for v in obj:
            size += size_r(v)
    elif isinstance(obj, dict):
        for v in obj.values():
            size += size_r(v)
    else:
        size += sys.getsizeof(obj)
    return size


def slice_to_redis_range(slice_):
    if slice_.step is not None and slice_.step != 1:
        raise NotImplementedError("Slice step not implemented yet")
    if slice_.stop == 0:
        return range(0, 0)
    start = slice_.start or 0
    stop = (slice_.stop or 0) - 1
    return range(start, stop)


def camel_case(string):
    return "".join([s.capitalize() for s in re.split(r"[\W\-_]+", string)])
