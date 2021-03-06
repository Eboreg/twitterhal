from types import ModuleType
from typing import Any, Dict, Optional, Type, Union

from megahal.megahal import DBInstance as MegaHALDBInstance

from twitterhal.conf import default_settings
from twitterhal.engine import DBInstance
from twitterhal.database import BaseDatabase


def setting_str(key: Optional[str], value: str, indent: int) -> str: ...


class Settings:
    default_settings: Dict[str, Any]
    is_setup: bool

    def __getattr__(self, name: str) -> Any: ...
    def __init__(self): ...
    def __setattr__(self, key: str, value: Any): ...
    def __str__(self) -> str: ...
    def get(self, key: str, default: Any) -> Any: ...
    def get_database_class(self) -> Type[DBInstance]: ...
    def get_megahal_database_class(self) -> Type[MegaHALDBInstance]: ...
    def setup(self, settings_module: Union[str, ModuleType, None], settings_dict: Dict[str, Any]): ...


for key in dir(default_settings):
    if key.isupper():
        value = getattr(default_settings, key)
        setattr(Settings, key, value)


settings: Settings
