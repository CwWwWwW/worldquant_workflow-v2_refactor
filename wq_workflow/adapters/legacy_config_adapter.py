from __future__ import annotations

from typing import Any


def config_get(config: Any, field: str, default: Any = None) -> Any:
    if isinstance(config, dict):
        return config.get(field, default)
    return getattr(config, field, default)
