import argparse
import logging

from twitterhal.conf import settings
from twitterhal.engine import TwitterHAL, run


def init_logging(loglevel=logging.ERROR):
    logging.basicConfig(
        format="%(asctime)s: [%(funcName)s: %(lineno)d] %(message)s", level=loglevel, datefmt="%H:%M:%S"
    )
    return logging.getLogger(__package__)


class CommandLine:
    def __init__(self, twitterhal_class=TwitterHAL):
        self.TwitterHAL = twitterhal_class

        self.parser = argparse.ArgumentParser(add_help=False)
        self.parser.add_argument(
            "-s", "--settings", dest="settings_module",
            help="Python path to settings module. If omitted, we try looking for it in the "
                 "'TWITTERHAL_SETTINGS_MODULE' environment variable."
        )
        self.parser.add_argument("-d", "--debug", action="store_true", help="More verbose logging output")
        self.parser.add_argument(
            "-m", "--include-mentions", action="store_true",
            help="Include all mentions in replies (rather than just the handle we're replying to)"
        )

        mutex = self.parser.add_mutually_exclusive_group()
        mutex.add_argument("-r", "--run", action="store_true", help="Run the bot!")
        mutex.add_argument("--chat", action="store_true", help="Chat with the bot")
        mutex.add_argument("--stats", action="store_true", help="Display some stats")
        mutex.add_argument("--print-config", action="store_true", help="Print current parsed config")

    def __enter__(self):
        self.setup()
        return self

    def __exit__(self, *args, **kwargs):
        pass

    def setup(self, *args, **kwargs):
        self.args = self.parser.parse_args()

        settings.setup(settings_module=self.args.settings_module)

        if self.args.debug:
            logger = init_logging(logging.DEBUG)
            logger.debug("TESTING DEBUG LOGGING")
        elif self.args.run:
            logger = init_logging(logging.INFO)
        else:
            logger = init_logging()

        self.init_megahal = self.args.run or self.args.stats or self.args.chat

    def run(self, *args, **kwargs):
        if self.init_megahal:
            print("Initializing MegaHAL, this could take a moment ...")

        with self.TwitterHAL(init_megahal=self.init_megahal) as self.hal:
            if self.args.chat:
                self.hal.megahal.interact()
            elif self.args.stats:
                self.print_stats()
            elif self.args.print_config:
                print(settings)
            elif self.args.run:
                run(self.hal)
            else:
                self.parser.print_help()

    def print_stats(self, *args, **kwargs):
        print("Posted random tweets: %d" % len(self.hal.db.posted_tweets.original_posts))
        print("Earliest random tweet date: %s" % self.hal.db.posted_tweets.original_posts.earliest_date)
        print("Latest random tweet date: %s" % self.hal.db.posted_tweets.original_posts.latest_date)
        print("Posted reply tweets: %d" % len(self.hal.db.posted_tweets.replies))
        print("Earliest random tweet date: %s" % self.hal.db.posted_tweets.replies.earliest_date)
        print("Latest random tweet date: %s" % self.hal.db.posted_tweets.replies.latest_date)
        print("Size of brain: %d" % self.hal.megahal.brainsize)


def main():
    with CommandLine() as cli:
        cli.run()
