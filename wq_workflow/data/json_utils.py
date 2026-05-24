from __future__ import annotations

import json
import math
from typing import Any


def to_jsonable(obj: Any) -> Any:
    if obj is None:
        return None
    if isinstance(obj, (str, bool, int)):
        return obj
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if hasattr(obj, "item"):
        try:
            return to_jsonable(obj.item())
        except Exception:
            return None
    if isinstance(obj, dict):
        return {str(k): to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [to_jsonable(v) for v in obj]
    try:
        return str(obj)
    except Exception:
        return None


def json_dumps_safe(obj: Any) -> str:
    try:
        return json.dumps(to_jsonable(obj), ensure_ascii=False, default=str)
    except Exception:
        return "{}"


def json_loads_safe(text: str | None, default: Any = None) -> Any:
    if default is None:
        default = {}
    if not text:
        return default
    try:
        return json.loads(text)
    except Exception:
        return default


def safe_float(value: Any, default: Any = None) -> float | Any:
    try:
        if value is None or value == "":
            return default
        v = float(value)
        return v if math.isfinite(v) else default
    except Exception:
        return default


def safe_int(value: Any, default: Any = None) -> int | Any:
    try:
        if value is None or value == "":
            return default
        return int(value)
    except Exception:
        return default
