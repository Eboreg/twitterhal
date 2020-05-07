import importlib
import os
import sys
import warnings
from copy import deepcopy
from types import ModuleType

from twitterhal.conf import default_settings


def setting_str(key=None, value="", indent=0):
    ret = " " * indent
    if key:
        ret += "%s=" % key
    if isinstance(value, dict):
        if len(value) == 0:
            ret += "{}"
        else:
            ret += "{\n"
            ret += ",\n".join([setting_str(key=k, value=v, indent=indent + 4) for k, v in value.items()])
            ret += "\n" + " " * indent + "}"
    elif isinstance(value, list):
        if len(value) == 0:
            ret += "[]"
        else:
            ret += "[\n"
            too_long = False
            if len(value) > 10:
                value = value[:10]
                too_long = True
            ret += ",\n".join([setting_str(value=v, indent=indent + 4) for v in value])
            if too_long:
                ret += "\n" + " " * (indent + 4) + "... (Too many values to show)"
            ret += "\n" + " " * indent + "]"
    elif isinstance(value, str):
        ret += '"%s"' % value
    else:
        ret += str(value)
    return ret


class Settings:
    """TwitterHAL settings

    Heavily inspired by django.conf.

    To inject your own settings, supply a settings module and/or settings dict
    (values in dict take precendence) before trying to access settings. Or set
    environment variable "TWITTERHAL_SETTINGS_MODULE" to the path of your
    settings module, and it will be taken care of for you.
    """

    def __init__(self):
        self.is_setup = False
        self.default_settings = {}

    def setup(self, settings_module=None, settings_dict={}):
        if self.is_setup:
            return

        assert settings_module is None or isinstance(settings_module, (ModuleType, str)), \
            "settings_module must be either None, a string, or a module"
        assert isinstance(settings_dict, dict), "settings_dict must be a dict"

        for key in dir(default_settings):
            if key.isupper():
                value = getattr(default_settings, key)
                setattr(self, key, value)
                self.default_settings[key] = value

        if not settings_module:
            settings_module = os.environ.get("TWITTERHAL_SETTINGS_MODULE", "")

        if settings_module:
            if isinstance(settings_module, str):
                try:
                    settings_module = importlib.import_module(settings_module)
                except ModuleNotFoundError:
                    sys.path.append(os.getcwd())
                    settings_module = importlib.import_module(settings_module)
            for setting in dir(settings_module):
                if setting.isupper():
                    setattr(self, setting, getattr(settings_module, setting))

        for setting, value in settings_dict.items():
            setattr(self, setting, value)

        # Run some value checks
        if self.SCREEN_NAME == "":
            warnings.warn("settings.SCREEN_NAME cannot be empty")

        if self.DETECTLANGUAGE_API_KEY:
            try:
                import detectlanguage  # noqa
            except ImportError:
                warnings.warn("settings.DETECTLANGUAGE_API_KEY was set, but detectlanguage could not be imported")

        self.is_setup = True

    def __setattr__(self, key, value):
        if key.isupper() and key in self.default_settings and isinstance(self.default_settings[key], dict):
            assert isinstance(value, dict), "Cannot replace a dict setting with a non-dict value"
            new_value = deepcopy(self.default_settings[key])
            new_value.update(value)
            value = new_value
        super().__setattr__(key, value)

    def __getattr__(self, key):
        if key.isupper() and not self.is_setup:
            self.setup()
            return getattr(self, key)
        raise AttributeError("settings has no attribute %s" % key)

    def __str__(self):
        ret = []
        for k, v in self.__dict__.items():
            if k.isupper() and not k.startswith("_"):
                ret.append(setting_str(key=k, value=v))
        return "\n".join(ret)

    def get(self, key, default):
        return getattr(self, key, default)

    def get_database_class(self):
        mod, klass = self.DATABASE["class"].rsplit(".", maxsplit=1)
        return getattr(importlib.import_module(mod), klass)

    def get_megahal_database_class(self):
        mod, klass = self.MEGAHAL_DATABASE["class"].rsplit(".", maxsplit=1)
        return getattr(importlib.import_module(mod), klass)


settings = Settings()
