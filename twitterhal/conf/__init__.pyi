from types import ModuleType
from typing import Any, Dict, Optional, Type, Union

from twitterhal.engine import DBInstance


def setting_str(key: Optional[str], value: str, indent: int) -> str:
    ...


class Settings:
    is_setup: bool

    def setup(self, settings_module: Union[str, ModuleType, None] = None, settings_dict: Dict[str, Any] = {}):
        ...

    def __getattr__(self, name: str) -> Any:
        ...

    def get_database_class(self) -> Type[DBInstance]:
        ...


settings: Settings
