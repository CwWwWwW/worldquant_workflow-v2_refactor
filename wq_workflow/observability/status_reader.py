from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .utils import safe_float_value


class StatusReader:
    def read_json_status(self, path: str | Path) -> dict[str, Any]:
        ok, payload, warnings = self.read_status_if_exists(path)
        if not ok and warnings:
            return {"warnings": warnings}
        return payload

    def read_status_if_exists(self, path: str | Path) -> tuple[bool, dict[str, Any], list[str]]:
        target = Path(path)
        warnings: list[str] = []
        try:
            if not target.exists():
                return False, {}, [f"status_missing:{target}"]
            text = target.read_text(encoding="utf-8-sig")
            payload = json.loads(text)
            if not isinstance(payload, dict):
                return False, {}, [f"status_not_object:{target}"]
            return True, payload, warnings
        except json.JSONDecodeError as exc:
            return False, {}, [f"status_json_corrupt:{target}:{exc}"]
        except Exception as exc:
            return False, {}, [f"status_read_failed:{target}:{exc}"]

    def is_stale(self, path: str | Path, max_age_seconds: int) -> bool:
        target = Path(path)
        try:
            if not target.exists():
                return True
            mtime = datetime.fromtimestamp(target.stat().st_mtime, UTC)
            return (datetime.now(UTC) - mtime).total_seconds() > max(0, int(max_age_seconds))
        except Exception:
            return True

    def get_mtime_iso(self, path: str | Path) -> str | None:
        target = Path(path)
        try:
            if not target.exists():
                return None
            return datetime.fromtimestamp(target.stat().st_mtime, UTC).isoformat()
        except Exception:
            return None

    def safe_extract_number(self, payload: dict[str, Any], keys: list[str], default: Any = None) -> Any:
        current: Any = payload if isinstance(payload, dict) else {}
        for key in keys:
            if not isinstance(current, dict) or key not in current:
                return default
            current = current.get(key)
        if current is None or current == "":
            return default
        return safe_float_value(current, default)

    def safe_extract_status(self, payload: dict[str, Any], keys: list[str], default: Any = None) -> Any:
        current: Any = payload if isinstance(payload, dict) else {}
        for key in keys:
            if not isinstance(current, dict) or key not in current:
                return default
            current = current.get(key)
        return default if current is None else current
