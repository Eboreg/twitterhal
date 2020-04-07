import configparser
import datetime
import html
import os
import re
from typing import TYPE_CHECKING, cast

import emoji

if TYPE_CHECKING:
    from typing import Any, Dict, List

    class ConfigParserExtended(configparser.ConfigParser):
        def gettimelist(self, *args, **kwargs):
            ...

EMOJI_REGEX = emoji.get_emoji_regexp()
URL_REGEX = r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+"


def split_to_sentences(phrase: str) -> "List[str]":
    sentences = []
    matches = re.split(r"([.?!]+)", phrase)
    matches_enum = enumerate(matches)
    for _, match in matches_enum:
        sentence = re.sub(r"['\"]", "", match)
        sentence = sentence.strip().capitalize()
        try:
            _, punctuation = next(matches_enum)
            sentence += punctuation
        except StopIteration:
            pass
        if sentence:
            sentences.append(sentence)
    return sentences


def capitalize(phrase: str) -> str:
    return " ".join(split_to_sentences(phrase))


def split_list_to_sentences(phrases: "List[str]") -> "List[List[str]]":
    start_idx = 0
    sentences = []
    for idx, word in enumerate(phrases):
        if word[:1] in ".?!" or idx == len(phrases) - 1:
            sentences.append(phrases[start_idx:idx + 1])
            start_idx = idx + 1
    return sentences


def strip_phrase(phrase: str) -> str:
    # Strip emojis
    phrase = re.sub(EMOJI_REGEX, "", phrase)
    # Unescape HTML entities
    phrase = html.unescape(phrase)
    # Strip URLs and mentions
    phrase = re.sub(URL_REGEX, "", phrase, flags=re.IGNORECASE)
    phrase = re.sub(r"@\w+", "", phrase)
    # Strip hashtags
    phrase = re.sub(r"#\w+", "", phrase)
    # Strip quotation marks
    phrase = re.sub(r"[”\"]", "", phrase)
    # Strip lines, stars & dots
    phrase = re.sub(r"\s*[|•*]\s*", " ", phrase)
    # Remote "RT : ", denoting retweet (it used to be a @handle there before
    # we stripped it above)
    phrase = re.sub(r"^rt : ", "", phrase, flags=re.IGNORECASE)
    # Convert non-space whitespace (\n, \t etc) to space
    phrase = re.sub(r"\s", " ", phrase)
    # Strip superfluous whitespace
    phrase = re.sub(r"\s{2,}", " ", phrase)
    # Remove trailing ellipsis + sentence that might have been cut off with it
    try:
        if phrase.strip()[-1] == "…":
            phrase = " ".join(split_to_sentences(phrase)[:-1])
    except IndexError:
        pass
    return phrase.strip()


def parse_time_string_list(string: str) -> "List[datetime.time]":
    result = []
    times = re.split(r",\s*", string)
    for t in times:
        try:
            result.append(datetime.datetime.strptime(t, "%H:%M:%S").time())
        except ValueError:
            result.append(datetime.datetime.strptime(t, "%H:%M").time())
    return result


def get_config(
    locations: "List[str]" = ["twitterhal.cfg", os.path.expanduser("~/.config/twitterhal.cfg"), "setup.cfg"]
) -> "Dict[str, Any]":
    # ConfigParser may raise NoSectionError with str attribute `section`, or
    # NoOptionError with str attributes `option` and `section`
    # pylint: disable=no-member
    result: "Dict[str, Any]" = {"twitterhal": {}, "twitter": {}, "megahal": {}}
    config = cast("ConfigParserExtended", configparser.ConfigParser(converters={"timelist": parse_time_string_list}))
    config.read(locations)
    result["twitterhal"]["screen_name"] = config.get("twitterhal", "screen_name")
    result["twitterhal"]["include_mentions"] = config.getboolean("twitterhal", "include_mentions", fallback=False)
    random_post_times = config.gettimelist("twitterhal", "random_post_times", fallback=None)
    if random_post_times:
        result["twitterhal"]["random_post_times"] = random_post_times
    result["twitter"] = dict(config.items("twitter"))
    if config.has_section("megahal"):
        result["megahal"] = dict(config.items("megahal"))
    return result
