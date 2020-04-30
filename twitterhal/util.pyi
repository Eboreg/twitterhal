import datetime
from typing import List, Pattern


emoji_pattern: Pattern[str]
hashtag_pattern: Pattern[str]
url_pattern: Pattern[str]


def parse_time_string_list(string: str) -> List[datetime.time]: ...
def strip_phrase(phrase: str) -> str: ...
