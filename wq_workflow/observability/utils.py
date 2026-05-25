from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from wq_workflow.data.json_utils import safe_float, safe_int, to_jsonable


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def json_safe(value: Any) -> Any:
    return to_jsonable(value)


def clean_dict(value: Any) -> dict[str, Any]:
    cleaned = to_jsonable(value if isinstance(value, dict) else {})
    return cleaned if isinstance(cleaned, dict) else {}


def clean_list(value: Any) -> list[Any]:
    cleaned = to_jsonable(value if isinstance(value, list) else [])
    return cleaned if isinstance(cleaned, list) else []


def as_number(value: Any, default: int | float | None = None) -> int | float | None:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    numeric = safe_float(value, default)
    return numeric


def atomic_write_json(path: str | Path, payload: Any, *, backup_corrupt: bool = False) -> dict[str, Any]:
    target = Path(path)
    backups: list[str] = []
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        if backup_corrupt and target.exists():
            try:
                json.loads(target.read_text(encoding="utf-8-sig"))
            except Exception:
                backup = target.with_name(f"{target.name}.broken.{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}.bak")
                shutil.copyfile(target, backup)
                backups.append(str(backup))
        tmp = target.with_name(f".{target.name}.tmp")
        tmp.write_text(json.dumps(to_jsonable(payload), ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        tmp.replace(target)
        return {"ok": True, "path": str(target), "backups": backups}
    except Exception as exc:
        return {"ok": False, "path": str(target), "backups": backups, "error": str(exc)}


def safe_int_value(value: Any, default: int = 0) -> int:
    return int(safe_int(value, default) or 0)


def safe_float_value(value: Any, default: float = 0.0) -> float:
    return float(safe_float(value, default) or 0.0)
