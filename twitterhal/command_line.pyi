from typing import Type, TypeVar

from twitterhal import TwitterHAL

TH = TypeVar("TH", bound=TwitterHAL)


def init_logging(loglevel: int):
    ...


def main():
    ...


class CommandLine:
    def __init__(self, twitterhal_class: Type[TH]):
        ...

    def print_stats(self, *args, **kwargs):
        ...

    def run(self, *args, **kwargs):
        ...

    def setup(self, *args, **kwargs):
        ...

    def __exit__(self, *args, **kwargs):
        ...

    def __enter__(self):
        ...
