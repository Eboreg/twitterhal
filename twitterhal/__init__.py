from twitterhal.engine import TwitterHAL


__version__ = "0.6.2"
VERSION = tuple(map(int, __version__.split(".")))

__all__ = ["TwitterHAL", "__version__", "VERSION"]
