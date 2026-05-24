from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .lifecycle import ModelLifecycleStatus, default_weight_for_status, expires_at_iso, is_terminal_status, utc_now_iso


def _loads(value: Any, default: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return default
    return value if value is not None else default


def _dumps(value: Any) -> str:
    try:
        from .events import json_dumps_safe
        return json_dumps_safe(value)
    except Exception:
        return json.dumps(value, ensure_ascii=False, default=str)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_json(path: Path, payload: dict[str, Any]) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_dumps(payload), encoding="utf-8")
        return True
    except Exception:
        return False


class RegistryAdapter:
    def __init__(self, model_registry: Any | None = None, db_conn: sqlite3.Connection | None = None, db_path: str | Path | None = None, model_root: str | Path | None = None, logger: Any | None = None, root: str | Path | None = None) -> None:
        self.registry = model_registry
        self.conn = db_conn or getattr(model_registry, "conn", None)
        self.db_path = Path(db_path) if db_path is not None else getattr(model_registry, "db_path", None)
        if self.db_path is not None:
            self.db_path = Path(self.db_path)
        if model_root is not None:
            self.models_root = Path(model_root)
        elif model_registry is not None and getattr(model_registry, "models_root", None) is not None:
            self.models_root = Path(model_registry.models_root)
        else:
            from wq_workflow.paths import ROOT
            self.models_root = Path(root or ROOT) / "runtime" / "models"
        self.logger = logger or getattr(model_registry, "logger", None)

    def _warn(self, message: str, *args: Any) -> None:
        try:
            if self.logger is not None:
                self.logger.warning(message, *args)
        except Exception:
            pass

    def _execute(self, sql: str, params: tuple[Any, ...]) -> bool:
        if self.registry is not None and hasattr(self.registry, "_execute"):
            return bool(self.registry._execute(sql, params))
        if self.conn is None and self.db_path is None:
            return True
        conn = self.conn
        close = False
        try:
            if conn is None:
                assert self.db_path is not None
                self.db_path.parent.mkdir(parents=True, exist_ok=True)
                conn = sqlite3.connect(self.db_path)
                close = True
            conn.execute(sql, params)
            conn.commit()
            return True
        except Exception as exc:
            self._warn("registry adapter DB write failed: %s", exc)
            return False
        finally:
            if close and conn is not None:
                conn.close()

    def _fetch_all(self, sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
        if self.registry is not None and hasattr(self.registry, "_fetch_all"):
            return [dict(r) for r in self.registry._fetch_all(sql, params)]
        if self.conn is None and self.db_path is None:
            return []
        conn = self.conn
        close = False
        try:
            if conn is None:
                assert self.db_path is not None
                conn = sqlite3.connect(self.db_path)
                close = True
            conn.row_factory = sqlite3.Row
            return [dict(r) for r in conn.execute(sql, params).fetchall()]
        except Exception as exc:
            self._warn("registry adapter DB read failed: %s", exc)
            return []
        finally:
            if close and conn is not None:
                conn.close()

    def _normalize_metadata(self, meta: dict[str, Any] | None) -> dict[str, Any] | None:
        if not meta:
            return None
        meta = dict(meta)
        raw = _loads(meta.get("raw_payload"), {})
        if not isinstance(raw, dict):
            raw = {}
        meta["raw_payload"] = raw
        status = raw.get("lifecycle_status") or meta.get("lifecycle_status") or ModelLifecycleStatus.SHADOW.value
        raw.setdefault("lifecycle_status", status)
        raw.setdefault("model_weight", default_weight_for_status(status))
        raw.setdefault("expires_at", meta.get("expires_at") or expires_at_iso(14))
        meta["lifecycle_status"] = raw.get("lifecycle_status")
        meta["model_weight"] = float(raw.get("model_weight") or 0.0)
        meta["expires_at"] = raw.get("expires_at")
        return meta

    def _metadata_path(self, task_name: str, model_version: str) -> Path:
        return self.models_root / str(task_name or "") / str(model_version or "") / "metadata.json"

    def _active_path(self, task_name: str) -> Path:
        if self.registry is not None and hasattr(self.registry, "_active_pointer_path"):
            try:
                return Path(self.registry._active_pointer_path(task_name))
            except Exception:
                pass
        return self.models_root / str(task_name or "") / "active_model.json"

    def get_active_metadata(self, task_name: str) -> dict[str, Any] | None:
        try:
            if self.registry is not None and hasattr(self.registry, "get_active_metadata"):
                meta = self.registry.get_active_metadata(task_name)
            else:
                rows = self._fetch_all("SELECT * FROM ml_model_registry WHERE task_name = ? AND is_active = 1 ORDER BY created_at DESC LIMIT 1", (str(task_name or ""),))
                meta = dict(rows[0]) if rows else _read_json(self._active_path(task_name))
            return self._normalize_metadata(meta)
        except Exception as exc:
            self._warn("get active metadata failed: %s", exc)
            return None

    def _update_raw_payload(self, task_name: str, model_version: str, updater: dict[str, Any]) -> bool:
        meta = None
        if self.registry is not None and hasattr(self.registry, "get_model_metadata"):
            meta = self.registry.get_model_metadata(task_name, model_version)
        if not meta:
            rows = self._fetch_all("SELECT * FROM ml_model_registry WHERE task_name = ? AND model_version = ?", (str(task_name or ""), str(model_version or "")))
            meta = dict(rows[0]) if rows else _read_json(self._metadata_path(task_name, model_version))
        if not meta:
            return False
        raw = _loads(meta.get("raw_payload"), {})
        if not isinstance(raw, dict):
            raw = {}
        raw.update(updater)
        raw["updated_at"] = utc_now_iso()
        meta["raw_payload"] = raw
        if "lifecycle_status" in updater:
            meta["lifecycle_status"] = updater["lifecycle_status"]
        if "model_weight" in updater:
            meta["model_weight"] = updater["model_weight"]
        meta_path = self._metadata_path(task_name, model_version)
        if meta_path.exists():
            _write_json(meta_path, meta)
        active = _read_json(self._active_path(task_name))
        if active and str(active.get("model_version") or "") == str(model_version or ""):
            active_raw = _loads(active.get("raw_payload"), {})
            if not isinstance(active_raw, dict):
                active_raw = {}
            active_raw.update(raw)
            active["raw_payload"] = active_raw
            active.update({k: v for k, v in updater.items() if k in {"lifecycle_status", "model_weight", "expires_at", "disable_reason"}})
            _write_json(self._active_path(task_name), active)
        return self._execute("UPDATE ml_model_registry SET raw_payload = ? WHERE task_name = ? AND model_version = ?", (_dumps(raw), str(task_name or ""), str(model_version or "")))

    def mark_lifecycle(self, task_name: str, model_version: str, status: str, reason: str = "") -> bool:
        status = str(status or ModelLifecycleStatus.SHADOW.value)
        payload = {"lifecycle_status": status, "model_weight": default_weight_for_status(status), "lifecycle_reason": reason, "expires_at": expires_at_iso(14)}
        if status == ModelLifecycleStatus.DISABLED.value:
            payload["disable_reason"] = reason
        ok = self._update_raw_payload(task_name, model_version, payload)
        if status in {ModelLifecycleStatus.DISABLED.value, ModelLifecycleStatus.EXPIRED.value, ModelLifecycleStatus.ROLLED_BACK.value}:
            self._execute("UPDATE ml_model_registry SET is_active = 0 WHERE task_name = ? AND model_version = ?", (str(task_name or ""), str(model_version or "")))
        return ok

    def update_model_weight(self, task_name: str, model_version: str, weight: float) -> bool:
        clamped = max(0.0, min(1.0, float(weight or 0.0)))
        return self._update_raw_payload(task_name, model_version, {"model_weight": clamped})

    def disable_active_model(self, task_name: str, reason: str = "") -> bool:
        meta = self.get_active_metadata(task_name)
        version = str((meta or {}).get("model_version") or "")
        if version:
            self._update_raw_payload(task_name, version, {"lifecycle_status": ModelLifecycleStatus.DISABLED.value, "model_weight": 0.0, "disable_reason": reason})
        if self.registry is not None and hasattr(self.registry, "disable_active_model"):
            return bool(self.registry.disable_active_model(task_name, reason=reason))
        active_path = self._active_path(task_name)
        if active_path.exists():
            backup = active_path.with_name(f"active_model.disabled.{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}.json")
            try:
                backup.write_text(active_path.read_text(encoding="utf-8"), encoding="utf-8")
            except Exception as exc:
                self._warn("active pointer backup failed: %s", exc)
        file_ok = _write_json(active_path, {"task_name": str(task_name or ""), "is_active": 0, "disabled_at": utc_now_iso(), "disabled_reason": reason, "raw_payload": {"lifecycle_status": "disabled", "model_weight": 0.0}})
        db_ok = self._execute("UPDATE ml_model_registry SET is_active = 0 WHERE task_name = ?", (str(task_name or ""),))
        return bool(file_ok and db_ok)

    def list_valid_previous_models(self, task_name: str) -> list[dict[str, Any]]:
        active = self.get_active_metadata(task_name) or {}
        current = str(active.get("model_version") or "")
        if self.registry is not None and hasattr(self.registry, "list_models"):
            rows = self.registry.list_models(task_name)
        else:
            rows = self._fetch_all("SELECT * FROM ml_model_registry WHERE task_name = ? ORDER BY created_at DESC", (str(task_name or ""),))
        out: list[dict[str, Any]] = []
        for row in rows or []:
            meta = self._normalize_metadata(dict(row)) or {}
            version = str(meta.get("model_version") or "")
            raw = meta.get("raw_payload") if isinstance(meta.get("raw_payload"), dict) else {}
            if not version or version == current:
                continue
            if is_terminal_status(raw.get("lifecycle_status") or meta.get("lifecycle_status")):
                continue
            model_path = Path(str(meta.get("model_path") or self.models_root / str(task_name or "") / version / "model.joblib"))
            if meta.get("model_path") and not model_path.exists():
                continue
            out.append(meta)
        return out

    def rollback_to_previous_active(self, task_name: str) -> bool:
        previous = self.list_valid_previous_models(task_name)
        if not previous:
            self.disable_active_model(task_name, reason="rollback_no_valid_previous_model")
            return False
        return self.rollback_to_version(task_name, str(previous[0].get("model_version") or ""))

    def rollback_to_version(self, task_name: str, model_version: str) -> bool:
        if not model_version:
            return False
        ok = False
        if self.registry is not None and hasattr(self.registry, "rollback_to_version"):
            ok = bool(self.registry.rollback_to_version(task_name, model_version))
        elif self.registry is not None and hasattr(self.registry, "activate_model"):
            ok = bool(self.registry.activate_model(task_name, model_version, reason="governance_rollback"))
        if ok:
            self._update_raw_payload(task_name, model_version, {"lifecycle_status": ModelLifecycleStatus.LIMITED_ACTIVE.value, "model_weight": default_weight_for_status(ModelLifecycleStatus.LIMITED_ACTIVE), "rollback_reason": "governance_rollback"})
        return ok

    def check_registry_consistency(self, task_name: str | None = None) -> dict[str, Any]:
        try:
            if self.registry is not None and hasattr(self.registry, "check_registry_consistency"):
                result = self.registry.check_registry_consistency(task_name)
            else:
                result = {"ok": True, "issues": []}
            issues = list(result.get("issues", [])) if isinstance(result, dict) else []
            for task in ([task_name] if task_name else []):
                if task:
                    meta = self.get_active_metadata(task)
                    raw = (meta or {}).get("raw_payload") if isinstance((meta or {}).get("raw_payload"), dict) else {}
                    if raw.get("lifecycle_status") not in {None, *[s.value for s in ModelLifecycleStatus]}:
                        issues.append({"task_name": task, "issue": "invalid_lifecycle_status", "model_version": (meta or {}).get("model_version")})
            return {"ok": not issues, "issues": issues}
        except Exception as exc:
            self._warn("registry consistency check failed: %s", exc)
            return {"ok": False, "issues": [{"issue": "registry_check_exception", "error": str(exc)}]}

    def repair_registry(self, task_name: str | None = None) -> dict[str, Any]:
        try:
            if self.registry is not None and hasattr(self.registry, "repair_registry"):
                return self.registry.repair_registry(task_name)
        except Exception as exc:
            self._warn("registry repair failed: %s", exc)
            return {"ok": False, "error": str(exc), "repairs": []}
        return {"ok": True, "repairs": []}
