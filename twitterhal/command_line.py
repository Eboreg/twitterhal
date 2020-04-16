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
        self.parser.add_argument(
            "-f", "--force", action="store_true", help="Try and force stuff, even if TwitterHAL doesn't want to"
        )

        self.mutex = self.parser.add_mutually_exclusive_group()
        self.mutex.add_argument("-r", "--run", action="store_true", help="Run the bot!")
        self.mutex.add_argument("--chat", action="store_true", help="Chat with the bot")
        self.mutex.add_argument("--stats", action="store_true", help="Display some stats")
        self.mutex.add_argument("--print-config", action="store_true", help="Print current parsed config")
        self.mutex.add_argument("--post-random", action="store_true", help="Post a new random tweet")

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

        self.init_megahal = self.args.run or self.args.chat or self.args.post_random

    def run(self, *args, **kwargs):
        if self.init_megahal:
            print("Initializing MegaHAL, this could take a moment ...")

        with self.TwitterHAL(init_megahal=self.init_megahal, force=self.args.force) as self.hal:
            if self.args.chat:
                self.hal.megahal.interact()
            elif self.args.stats:
                self.print_stats()
            elif self.args.print_config:
                print(settings)
            elif self.args.post_random:
                self.hal.post_random_tweet()
            elif self.args.run:
                run(self.hal)
            elif not self.run_extra():
                self.parser.print_help()

    def run_extra(self, *args, **kwargs):
        """
        Plug in your extra runners here. Make sure this returns True if any
        of them were applicable and run.
        """
        return False

    def print_stats(self, *args, **kwargs):
        print("Posted random tweets:         %d" % len(self.hal.db.posted_tweets.original_posts))
        print("  - earliest date:            %s" % self.hal.db.posted_tweets.original_posts.earliest_date)
        print("  - latest date:              %s" % self.hal.db.posted_tweets.original_posts.latest_date)
        print("Posted reply tweets:          %d" % len(self.hal.db.posted_tweets.replies))
        print("  - earliest date:            %s" % self.hal.db.posted_tweets.replies.earliest_date)
        print("  - latest date:              %s" % self.hal.db.posted_tweets.replies.latest_date)
        print("Mentions:                     %d" % len(self.hal.db.mentions))
        print("  - unanswered:               %d" % len(self.hal.db.mentions.unanswered))


def main():
    with CommandLine() as cli:
        cli.run()
