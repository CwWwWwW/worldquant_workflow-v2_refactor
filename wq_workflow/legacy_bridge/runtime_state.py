from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from wq_workflow import paths

from .schema import RuntimeStateSnapshot
from .utils import atomic_write_json_direct, resolve_path, summarize_exception, summarize_payload, utc_now_iso

DEFAULT_RUNTIME_STATE_PATH = "runtime/status/runtime_state.json"


class RuntimeStateWriter:
    def __init__(self, path: str | Path = DEFAULT_RUNTIME_STATE_PATH, *, root: str | Path | None = None, enabled: bool = True) -> None:
        self.root = Path(root or paths.ROOT)
        self.path = resolve_path(self.root, path)
        self.enabled = bool(enabled)

    def build_default_snapshot(self) -> RuntimeStateSnapshot:
        return RuntimeStateSnapshot(current_state="UNKNOWN", raw_payload={"source": "legacy_iteration_observer"})

    def write_snapshot(self, snapshot: RuntimeStateSnapshot) -> bool:
        if not self.enabled:
            return False
        try:
            snapshot.updated_at = utc_now_iso()
            return atomic_write_json_direct(self.path, snapshot.to_dict())
        except Exception:
            return False

    def update_state(self, **kwargs: Any) -> RuntimeStateSnapshot:
        snapshot = RuntimeStateReader(self.path).read_snapshot()[1] or self.build_default_snapshot()
        for key, value in kwargs.items():
            if hasattr(snapshot, key):
                setattr(snapshot, key, value)
        snapshot.updated_at = utc_now_iso()
        snapshot.last_event_at = kwargs.get("last_event_at") or snapshot.last_event_at or snapshot.updated_at
        self.write_snapshot(snapshot)
        return snapshot

    def write_fail_open(self, snapshot_or_kwargs: RuntimeStateSnapshot | dict[str, Any] | None = None, **kwargs: Any) -> dict[str, Any]:
        try:
            if isinstance(snapshot_or_kwargs, RuntimeStateSnapshot):
                ok = self.write_snapshot(snapshot_or_kwargs)
                return {"ok": ok, "path": str(self.path)}
            data = dict(snapshot_or_kwargs or {}) if isinstance(snapshot_or_kwargs, dict) else {}
            data.update(kwargs)
            snapshot = self.update_state(**data)
            return {"ok": True, "path": str(self.path), "snapshot_id": snapshot.snapshot_id}
        except Exception as exc:
            return {"ok": False, "path": str(self.path), "error": summarize_exception(exc)}


class RuntimeStateReader:
    def __init__(self, path: str | Path = DEFAULT_RUNTIME_STATE_PATH, *, root: str | Path | None = None) -> None:
        self.root = Path(root or paths.ROOT)
        self.path = resolve_path(self.root, path)

    def read_raw(self) -> dict[str, Any]:
        ok, snapshot, warnings = self.read_snapshot()
        if not ok or snapshot is None:
            return {"warnings": warnings}
        return snapshot.to_dict()

    def read_snapshot(self) -> tuple[bool, RuntimeStateSnapshot | None, list[str]]:
        warnings: list[str] = []
        try:
            if not self.path.exists():
                return False, None, ["runtime_state_missing"]
            payload = json.loads(self.path.read_text(encoding="utf-8-sig"))
            if not isinstance(payload, dict):
                return False, None, ["runtime_state_not_object"]
            return True, RuntimeStateSnapshot.from_dict(summarize_payload(payload, max_payload_chars=20_000)), warnings
        except json.JSONDecodeError as exc:
            return False, None, [f"runtime_state_json_corrupt:{exc}"]
        except Exception as exc:
            return False, None, [f"runtime_state_read_failed:{summarize_exception(exc)}"]

    def is_stale(self, max_age_seconds: int) -> bool:
        try:
            if not self.path.exists():
                return True
            return (time.time() - self.path.stat().st_mtime) > max(0, int(max_age_seconds))
        except Exception:
            return True
