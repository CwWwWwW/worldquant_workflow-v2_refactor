from __future__ import annotations

from typing import Any


def config_flag(config: Any, name: str, default: bool = False) -> bool:
    return bool(getattr(config, name, default))


def config_value(config: Any, name: str, default: Any = None) -> Any:
    return getattr(config, name, default)
