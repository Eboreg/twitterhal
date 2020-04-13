import argparse
import configparser
import logging

from twitterhal.engine import TwitterHAL, run
from twitterhal.util import get_config


def init_logging(loglevel=logging.ERROR):
    logging.basicConfig(
        format="%(asctime)s: [%(funcName)s: %(lineno)d] %(message)s", level=loglevel, datefmt="%H:%M:%S"
    )
    return logging.getLogger(__package__)


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        "-c", "--config",
        help="Path to config file in ini format. If omitted, looks for ./twitterhal.cfg, ~/.config/twitterhal.cfg, "
             "and ./setup.cfg."
    )
    parser.add_argument("-d", "--debug", action="store_true", help="More verbose logging output")
    parser.add_argument(
        "-m", "--include-mentions", action="store_true",
        help="Include all mentions in replies (rather than just the handle we're replying to)"
    )

    mutex = parser.add_mutually_exclusive_group()
    mutex.add_argument("-r", "--run", action="store_true", help="Run the bot!")
    mutex.add_argument("--chat", action="store_true", help="Chat with the bot")
    mutex.add_argument("--stats", action="store_true", help="Display some stats")
    mutex.add_argument("--print-config", action="store_true", help="Print current parsed config")

    args = parser.parse_args()

    if args.debug:
        logger = init_logging(logging.DEBUG)
        logger.debug("TESTING DEBUG LOGGING")
    elif args.run:
        logger = init_logging(logging.INFO)
    else:
        logger = init_logging()

    try:
        if args.config:
            config = get_config([args.config])
        else:
            config = get_config()
    except configparser.Error as e:
        print("Arguments in config file missing or malformed! "
              "Please see README.md.")
        raise e

    with TwitterHAL(
        twitter_kwargs=config["twitter"], megahal_kwargs=config["megahal"], **config["twitterhal"]) as hal:
        if args.chat:
            hal.megahal.interact()
        elif args.stats:
            print("Posted random tweets: %d" % len(hal.db.posted_tweets.original_posts))
            print("Earliest random tweet date: %s" % hal.db.posted_tweets.original_posts.earliest_date)
            print("Latest random tweet date: %s" % hal.db.posted_tweets.original_posts.latest_date)
            print("Posted reply tweets: %d" % len(hal.db.posted_tweets.replies))
            print("Earliest random tweet date: %s" % hal.db.posted_tweets.replies.earliest_date)
            print("Latest trending tweet date: %s" % hal.db.posted_tweets.replies.latest_date)
            print("Size of brain: %d" % hal.megahal.brainsize)
        elif args.print_config:
            print("twitterhal:")
            for k, v in config["twitterhal"].items():
                print("  %s: %s" % (k, v))
            print("twitter:")
            for k, v in config["twitter"].items():
                print("  %s: %s" % (k, v))
            print("megahal:")
            for k, v in config["megahal"].items():
                print("  %s: %s" % (k, v))
        elif args.run:
            run(hal)
        else:
            parser.print_help()
