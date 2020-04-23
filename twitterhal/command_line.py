import argparse
import logging

from twitterhal.conf import settings
from twitterhal.engine import TwitterHAL
from twitterhal.runtime import runner


def init_logging(loglevel=logging.ERROR):
    logging.basicConfig(
        format="%(asctime)s: [%(funcName)s: %(lineno)d] %(message)s", level=loglevel, datefmt="%H:%M:%S"
    )
    return logging.getLogger(__package__)


class CommandLine:
    def __init__(self, twitterhal_class=TwitterHAL, settings_module=None):
        self.TwitterHAL = twitterhal_class

        if settings_module:
            settings.setup(settings_module=settings_module)

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
        self.parser.add_argument(
            "-t", "--test", action="store_true", help="Test mode; doesn't actually post anything"
        )

        self.mutex = self.parser.add_mutually_exclusive_group()
        self.mutex.add_argument("-r", "--run", action="store_true", help="Run the bot!")
        self.mutex.add_argument("--chat", action="store_true", help="Chat with the bot")
        self.mutex.add_argument("--stats", action="store_true", help="Display some stats")
        self.mutex.add_argument("--print-config", action="store_true", help="Print current parsed config")
        self.mutex.add_argument("--post-random", action="store_true", help="Post a new random tweet")
        self.mutex.add_argument(
            "--mark-mentions-answered", action="store_true",
            help="Fetch the latest mentions and mark them all as answered. Useful if you had to re-init the DB."
        )

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

    def get_hal_kwargs(self):
        return {"init_megahal": self.init_megahal, "force": self.args.force, "test": self.args.test}

    def run(self, *args, **kwargs):
        if self.args.chat:
            with self.TwitterHAL(**self.get_hal_kwargs()) as hal:
                hal.megahal.interact()
        elif self.args.stats:
            with self.TwitterHAL(**self.get_hal_kwargs()) as hal:
                self.print_stats(hal)
        elif self.args.print_config:
            print(settings)
        elif self.args.post_random:
            with self.TwitterHAL(**self.get_hal_kwargs()) as hal:
                hal.post_random_tweet()
        elif self.args.mark_mentions_answered:
            with self.TwitterHAL(**self.get_hal_kwargs()) as hal:
                hal.mark_mentions_answered()
        elif self.args.run:
            with self.TwitterHAL(**self.get_hal_kwargs()) as hal:
                runner.sleep_seconds = settings.RUNNER_SLEEP_SECONDS
                runner.run()
        elif not self.run_extra():
            self.parser.print_help()

    def run_extra(self, *args, **kwargs):
        """
        Plug in your extra routines here. Make sure this returns True if any
        of them were applicable and run. And wrap them in
        `self.TwitterHAL(**self.get_hal_kwargs()) as hal` if so is required.
        """
        return False

    def print_stats(self, hal, **kwargs):
        print("Posted random tweets:         %d" % len(hal.db.posted_tweets.original_posts))
        print("  - earliest date:            %s" % hal.db.posted_tweets.original_posts.earliest_date)
        print("  - latest date:              %s" % hal.db.posted_tweets.original_posts.latest_date)
        print("Posted reply tweets:          %d" % len(hal.db.posted_tweets.replies))
        print("  - earliest date:            %s" % hal.db.posted_tweets.replies.earliest_date)
        print("  - latest date:              %s" % hal.db.posted_tweets.replies.latest_date)
        print("Mentions:                     %d" % len(hal.db.mentions))
        print("  - unanswered:               %d" % len(hal.db.mentions.unanswered))


def main():
    with CommandLine() as cli:
        cli.run()


if __name__ == "__main__":
    main()
