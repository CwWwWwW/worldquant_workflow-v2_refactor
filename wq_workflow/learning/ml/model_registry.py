from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from .availability import require_joblib
from .feature_schema import FeatureSchema, SimpleFeatureSchema
from .safe_model_io import load_model, read_json, save_model, write_json


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _json(value: Any) -> str:
    try:
        from wq_workflow.data.json_utils import to_jsonable

        value = to_jsonable(value)
    except Exception:
        pass
    return json.dumps(value, ensure_ascii=False, allow_nan=False, default=str)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_json(path: Path, payload: dict[str, Any]) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_json(payload), encoding="utf-8")
        return True
    except Exception:
        return False


class ModelRegistry:
    def __init__(
        self,
        db_conn: sqlite3.Connection | None = None,
        model_root: str | Path | None = None,
        logger: Any | None = None,
        *,
        root: str | Path | None = None,
        storage: Any | None = None,
        db_path: str | Path | None = None,
    ) -> None:
        from wq_workflow.paths import ROOT, RUNTIME_DIR

        self.root = Path(root or ROOT)
        self.models_root = Path(model_root) if model_root is not None else (self.root / "runtime" / "models" if root is not None else RUNTIME_DIR / "models")
        self.conn = db_conn
        self.logger = logger
        self.storage = storage
        self.db_path = Path(db_path) if db_path is not None else getattr(getattr(storage, "config", None), "db_path", None)

    def _schema_payload(self, feature_schema: FeatureSchema | SimpleFeatureSchema | dict[str, Any] | None) -> dict[str, Any]:
        if isinstance(feature_schema, FeatureSchema):
            return feature_schema.to_dict()
        if isinstance(feature_schema, SimpleFeatureSchema):
            return feature_schema.to_feature_schema().to_dict()
        if isinstance(feature_schema, dict):
            if "schema_version" in feature_schema:
                return FeatureSchema.from_dict(feature_schema).to_dict()
            return SimpleFeatureSchema.from_json(feature_schema).to_feature_schema().to_dict()
        return FeatureSchema(schema_version="v1", feature_names=[]).to_dict()

    def _simple_schema(self, feature_schema: FeatureSchema | SimpleFeatureSchema | dict[str, Any] | None) -> SimpleFeatureSchema:
        if isinstance(feature_schema, SimpleFeatureSchema):
            return feature_schema
        payload = self._schema_payload(feature_schema)
        defaults = dict((payload.get("metadata") or {}).get("defaults") or {})
        return SimpleFeatureSchema(feature_names=list(payload.get("feature_names") or []), defaults=defaults)

    def _warn(self, message: str, *args: Any) -> None:
        try:
            if self.logger is not None:
                self.logger.warning(message, *args)
        except Exception:
            pass

    def _result(self, *, ok: bool, task_name: str, model_version: str, model_path: Path, error: str = "", **extra: Any) -> dict[str, Any]:
        payload = {
            "ok": bool(ok),
            "model_file_saved": bool(extra.pop("model_file_saved", False)),
            "feature_schema_saved": bool(extra.pop("feature_schema_saved", False)),
            "evaluation_saved": bool(extra.pop("evaluation_saved", False)),
            "metadata_saved": bool(extra.pop("metadata_saved", False)),
            "registry_written": bool(extra.pop("registry_written", False)),
            "active_model_written": bool(extra.pop("active_model_written", False)),
            "db_active_updated": bool(extra.pop("db_active_updated", False)),
            "model_path": str(model_path),
            "task_name": task_name,
            "model_version": model_version,
            "model_id": f"{task_name}:{model_version}" if task_name and model_version else "",
            "error": error,
        }
        payload.update(extra)
        return payload

    def save_model_version(
        self,
        task_name: str,
        model: Any,
        feature_schema: FeatureSchema | SimpleFeatureSchema | dict[str, Any] | None = None,
        *,
        model_version: str | None = None,
        train_sample_count: int = 0,
        evaluation: dict[str, Any] | None = None,
        metrics: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        model_type: str = "sklearn",
        raw_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        task = str(task_name or "")
        version = model_version or datetime.now().strftime("%Y%m%d%H%M%S") + "_" + uuid.uuid4().hex[:6]
        model_dir = self.models_root / task / version
        model_path = model_dir / "model.joblib"
        if require_joblib() is None:
            return None  # Preserve legacy dependency-unavailable fallback behavior.
        if not save_model(model, model_path, self.logger):
            return self._result(ok=False, task_name=task, model_version=version, model_path=model_path, error="model_file_save_failed")
        schema_obj = self._simple_schema(feature_schema)
        schema_payload = self._schema_payload(feature_schema)
        eval_payload = evaluation or metrics or {}
        gate = eval_payload.get("validation_gate") if isinstance(eval_payload.get("validation_gate"), dict) else {}
        meta = {
            "model_id": f"{task}:{version}",
            "task_name": task,
            "model_version": version,
            "model_path": str(model_path),
            "created_at": _now(),
            "train_sample_count": int(train_sample_count or 0),
            "validation_metric_json": eval_payload.get("metrics", eval_payload),
            "model_type": model_type,
            "feature_count": len(schema_obj.feature_names),
            "activated": False,
            "activation_reason": "not_activated",
            "validation_passed": bool(gate.get("passed", False)),
            "raw_payload": raw_payload or {},
        }
        if metadata:
            meta.update(metadata)
        if not write_json(model_dir / "feature_schema.json", schema_payload, self.logger):
            result = self._result(ok=False, task_name=task, model_version=version, model_path=model_path, error="feature_schema_save_failed", model_file_saved=True)
            result.update(meta)
            result["ok"] = False
            result["error"] = "feature_schema_save_failed"
            return result
        evaluation_saved = write_json(model_dir / "evaluation.json", eval_payload, self.logger)
        metadata_saved = write_json(model_dir / "metadata.json", meta, self.logger)
        registry_written = self._write_registry(meta, schema_obj, is_active=False)
        ok = bool(evaluation_saved and metadata_saved and registry_written)
        error = "" if ok else "evaluation_or_metadata_or_registry_write_failed"
        result = self._result(
            ok=ok,
            task_name=task,
            model_version=version,
            model_path=model_path,
            error=error,
            model_file_saved=True,
            feature_schema_saved=True,
            evaluation_saved=evaluation_saved,
            metadata_saved=metadata_saved,
            registry_written=registry_written,
        )
        result.update(meta)
        result["ok"] = ok
        result["error"] = error
        result["registry_written"] = registry_written
        return result

    def activate_model(self, task_name: str, model_version: str, *, reason: str = "validation_passed") -> bool:
        task = str(task_name or "")
        model_dir = self.models_root / task / str(model_version or "")
        metadata_path = model_dir / "metadata.json"
        meta = _read_json(metadata_path)
        if not meta:
            meta = self.get_model_metadata(task, model_version) or {}
        if not meta:
            return False
        schema_payload = read_json(model_dir / "feature_schema.json", self.logger) or {}
        schema = self._simple_schema(schema_payload)
        active_payload = dict(meta)
        active_payload.update({
            "activated": True,
            "activation_reason": reason,
            "activated_at": _now(),
            "feature_schema_json": _json(self._schema_payload(schema_payload)),
        })
        if not write_json(self.models_root / task / "active_model.json", active_payload, self.logger):
            return False
        meta.update({"activated": True, "activation_reason": reason, "activated_at": active_payload["activated_at"]})
        metadata_saved = write_json(metadata_path, meta, self.logger)
        db_deactivated = self._execute("UPDATE ml_model_registry SET is_active = 0 WHERE task_name = ?", (task,))
        registry_written = self._write_registry(active_payload, schema, is_active=True)
        ok = bool(metadata_saved and db_deactivated and registry_written)
        if not ok:
            self._warn("failed to fully activate model task=%s version=%s metadata_saved=%s db_deactivated=%s registry_written=%s", task, model_version, metadata_saved, db_deactivated, registry_written)
        return ok

    def deactivate_model(self, task_name: str) -> bool:
        task = str(task_name or "")
        active_path = self.models_root / task / "active_model.json"
        file_ok = write_json(active_path, {"task_name": task, "is_active": 0, "deactivated_at": _now()}, self.logger)
        db_ok = self._execute("UPDATE ml_model_registry SET is_active = 0 WHERE task_name = ?", (task,))
        return bool(file_ok and db_ok)

    def deactivate(self, task_name: str) -> None:
        self.deactivate_model(task_name)

    def rollback_to_version(self, task_name: str, model_version: str) -> bool:
        meta = self.get_model_metadata(task_name, model_version)
        if not meta:
            return False
        return self.activate_model(task_name, model_version, reason="rollback")

    def load_active_model(self, task_name: str) -> dict[str, Any] | None:
        active_path = self.models_root / str(task_name or "") / "active_model.json"
        if not active_path.exists():
            return None
        payload = read_json(active_path, self.logger)
        if not payload or payload.get("is_active") == 0:
            return None
        raw_payload = payload.get("raw_payload") if isinstance(payload.get("raw_payload"), dict) else _read_json(Path("__missing__"))
        if isinstance(payload.get("raw_payload"), str):
            try:
                raw_payload = json.loads(payload.get("raw_payload") or "{}")
            except Exception:
                raw_payload = {}
        lifecycle_status = str((raw_payload or {}).get("lifecycle_status") or payload.get("lifecycle_status") or "")
        if lifecycle_status in {"disabled", "expired", "rolled_back"}:
            self._warn("active model lifecycle status disallows loading for task=%s version=%s status=%s", task_name, payload.get("model_version"), lifecycle_status)
            return None
        model_path = payload.get("model_path") or str(self.models_root / str(task_name or "") / str(payload.get("model_version") or "") / "model.joblib")
        if not Path(model_path).exists():
            self._warn("active model file missing for task=%s path=%s", task_name, model_path)
            return None
        if self.conn is not None or self.db_path:
            rows = self._fetch_all(
                "SELECT * FROM ml_model_registry WHERE task_name = ? AND model_version = ?",
                (str(task_name or ""), str(payload.get("model_version") or "")),
            )
            if not rows:
                self._warn("active model pointer missing DB record for task=%s version=%s", task_name, payload.get("model_version"))
                return None
            if not any(int(row.get("is_active") or 0) == 1 for row in rows):
                self._warn("active model pointer DB record is not active for task=%s version=%s", task_name, payload.get("model_version"))
                return None
        model = load_model(model_path, self.logger)
        if model is None:
            return None
        schema_payload = payload.get("feature_schema_json")
        if not schema_payload:
            schema_payload = read_json(Path(model_path).parent / "feature_schema.json", self.logger)
        if isinstance(schema_payload, str):
            try:
                schema_data = json.loads(schema_payload)
            except Exception:
                return None
        elif isinstance(schema_payload, dict):
            schema_data = schema_payload
        else:
            schema_data = {}
        if not schema_data:
            self._warn("active model feature schema missing for task=%s version=%s", task_name, payload.get("model_version"))
            return None
        metrics_payload = payload.get("validation_metric_json")
        if isinstance(metrics_payload, str):
            try:
                metrics = json.loads(metrics_payload)
            except Exception:
                metrics = {}
        else:
            metrics = metrics_payload if isinstance(metrics_payload, dict) else {}
        return {
            "model": model,
            "feature_schema": FeatureSchema.from_dict(schema_data),
            "metrics": metrics,
            "model_version": payload.get("model_version", ""),
            "model_id": payload.get("model_id", ""),
            "payload": payload,
        }

    def get_model_metadata(self, task_name: str, model_version: str) -> dict[str, Any] | None:
        meta_path = self.models_root / str(task_name or "") / str(model_version or "") / "metadata.json"
        meta = _read_json(meta_path)
        if meta:
            return meta
        rows = self._fetch_all(
            "SELECT * FROM ml_model_registry WHERE task_name = ? AND model_version = ?",
            (str(task_name or ""), str(model_version or "")),
        )
        if not rows:
            return None
        row = dict(rows[0])
        row["raw_payload"] = self._loads(row.get("raw_payload"), {})
        row["validation_metric_json"] = self._loads(row.get("validation_metric_json"), {})
        return row

    def get_active_metadata(self, task_name: str) -> dict[str, Any] | None:
        rows = self._fetch_all(
            "SELECT * FROM ml_model_registry WHERE task_name = ? AND is_active = 1 ORDER BY created_at DESC LIMIT 1",
            (str(task_name or ""),),
        )
        if rows:
            return dict(rows[0])
        return read_json(self.models_root / str(task_name or "") / "active_model.json", self.logger)

    def list_models(self, task_name: str | None = None) -> list[dict[str, Any]]:
        if task_name:
            db_rows = self._fetch_all("SELECT * FROM ml_model_registry WHERE task_name = ? ORDER BY created_at DESC", (task_name,))
        else:
            db_rows = self._fetch_all("SELECT * FROM ml_model_registry ORDER BY created_at DESC", ())
        if db_rows:
            return db_rows
        roots = [self.models_root / task_name] if task_name else [p for p in self.models_root.glob("*") if p.is_dir()]
        out: list[dict[str, Any]] = []
        for root in roots:
            if not root.exists():
                continue
            for child in root.iterdir():
                if child.is_dir():
                    meta = _read_json(child / "metadata.json")
                    if meta:
                        out.append(meta)
        return sorted(out, key=lambda r: str(r.get("created_at", "")), reverse=True)

    def save_and_activate(
        self,
        task_name: str,
        model: Any,
        feature_schema: FeatureSchema | SimpleFeatureSchema,
        *,
        model_version: str | None = None,
        train_sample_count: int = 0,
        validation_metric: dict[str, Any] | None = None,
        raw_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        evaluation = {"metrics": validation_metric or {}, "validation_gate": {"passed": True, "reasons": []}}
        meta = self.save_model_version(task_name, model, feature_schema, model_version=model_version, train_sample_count=train_sample_count, evaluation=evaluation, metadata={"validation_passed": True}, raw_payload=raw_payload)
        if meta is None:
            return None
        if not meta.get("ok"):
            return meta
        activated = self.activate_model(task_name, meta["model_version"], reason="legacy_save_and_activate")
        active_payload = _read_json(self.models_root / task_name / "active_model.json")
        meta.update({
            "ok": bool(activated and active_payload),
            "active_model_written": bool(active_payload),
            "db_active_updated": bool(activated),
            "activated": bool(activated),
            "activation_error": "" if activated else "activate_model_failed",
        })
        if active_payload:
            meta.update(active_payload)
        return meta

    def _write_registry(self, payload: dict[str, Any], feature_schema: SimpleFeatureSchema, *, is_active: bool) -> bool:
        if self.conn is None and not self.db_path:
            return True
        return self._execute(
            """
            INSERT OR REPLACE INTO ml_model_registry
            (model_id, task_name, model_version, model_path, feature_schema_json, train_sample_count,
             validation_metric_json, is_active, created_at, raw_payload)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.get("model_id") or f"{payload.get('task_name')}:{payload.get('model_version')}",
                payload.get("task_name"),
                payload.get("model_version"),
                payload.get("model_path"),
                _json(feature_schema.to_feature_schema().to_dict()),
                int(payload.get("train_sample_count") or 0),
                _json(payload.get("validation_metric_json") or {}),
                1 if is_active else 0,
                payload.get("created_at") or _now(),
                _json(payload),
            ),
        )

    def _execute(self, sql: str, params: tuple[Any, ...]) -> bool:
        if self.conn is None and not self.db_path:
            return True
        if self.conn is not None:
            try:
                from wq_workflow.storage.schema import initialize_schema
                initialize_schema(self.conn)
                self.conn.execute(sql, params)
                self.conn.commit()
                return True
            except Exception as exc:
                self._warn("ML model registry DB write failed: %s", exc)
                return False
        conn = None
        try:
            from wq_workflow.storage.schema import initialize_schema
            conn = sqlite3.connect(self.db_path)
            initialize_schema(conn)
            conn.execute(sql, params)
            conn.commit()
            return True
        except Exception as exc:
            self._warn("ML model registry DB write failed: %s", exc)
            return False
        finally:
            if conn is not None:
                conn.close()

    def _fetch_all(self, sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
        if self.conn is None and not self.db_path:
            return []
        if self.conn is not None:
            try:
                from wq_workflow.storage.schema import initialize_schema
                self.conn.row_factory = sqlite3.Row
                initialize_schema(self.conn)
                return [dict(row) for row in self.conn.execute(sql, params).fetchall()]
            except Exception as exc:
                self._warn("ML model registry DB read failed: %s", exc)
                return []
        conn = None
        try:
            from wq_workflow.storage.schema import initialize_schema
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            initialize_schema(conn)
            return [dict(row) for row in conn.execute(sql, params).fetchall()]
        except Exception as exc:
            self._warn("ML model registry DB read failed: %s", exc)
            return []
        finally:
            if conn is not None:
                conn.close()

    def _active_pointer_path(self, task_name: str) -> Path:
        return self.models_root / str(task_name or "") / "active_model.json"

    def _schema_path_for(self, task_name: str, model_version: str, model_path: str | Path | None = None) -> Path:
        if model_path:
            return Path(model_path).parent / "feature_schema.json"
        return self.models_root / str(task_name or "") / str(model_version or "") / "feature_schema.json"

    def _tasks_for_check(self, task_name: str | None = None) -> list[str]:
        if task_name:
            return [str(task_name)]
        tasks = {str(row.get("task_name") or "") for row in self._fetch_all("SELECT DISTINCT task_name FROM ml_model_registry", ()) if row.get("task_name")}
        try:
            if self.models_root.exists():
                tasks.update(p.name for p in self.models_root.iterdir() if p.is_dir())
        except Exception:
            pass
        return sorted(t for t in tasks if t)

    def check_registry_consistency(self, task_name: str | None = None) -> dict[str, Any]:
        issues: list[dict[str, Any]] = []
        for task in self._tasks_for_check(task_name):
            active_rows = self._fetch_all(
                "SELECT * FROM ml_model_registry WHERE task_name = ? AND is_active = 1 ORDER BY created_at DESC",
                (task,),
            )
            if len(active_rows) > 1:
                issues.append({"task_name": task, "model_version": "", "issue": "multiple_active", "count": len(active_rows)})
            for row in active_rows:
                version = str(row.get("model_version") or "")
                model_path = str(row.get("model_path") or self.models_root / task / version / "model.joblib")
                if not Path(model_path).exists():
                    issues.append({"task_name": task, "model_version": version, "issue": "missing_model_file", "model_path": model_path})
                if not self._schema_path_for(task, version, model_path).exists():
                    issues.append({"task_name": task, "model_version": version, "issue": "schema_missing", "model_path": model_path})
            active_path = self._active_pointer_path(task)
            if active_path.exists():
                payload = read_json(active_path, self.logger)
                if not payload or payload.get("is_active") == 0:
                    continue
                version = str(payload.get("model_version") or "")
                model_path = str(payload.get("model_path") or self.models_root / task / version / "model.joblib")
                if not version or not Path(model_path).exists():
                    issues.append({"task_name": task, "model_version": version, "issue": "broken_active_pointer", "model_path": model_path})
                elif self.conn is not None or self.db_path:
                    rows = self._fetch_all(
                        "SELECT * FROM ml_model_registry WHERE task_name = ? AND model_version = ?",
                        (task, version),
                    )
                    if not rows:
                        issues.append({"task_name": task, "model_version": version, "issue": "missing_db_record", "model_path": model_path})
                    elif not any(int(row.get("is_active") or 0) == 1 for row in rows):
                        issues.append({"task_name": task, "model_version": version, "issue": "broken_active_pointer", "model_path": model_path})
                if not self._schema_path_for(task, version, model_path).exists():
                    issues.append({"task_name": task, "model_version": version, "issue": "schema_missing", "model_path": model_path})
        return {"ok": not issues, "issues": issues}

    def disable_active_model(self, task_name: str, reason: str = "") -> bool:
        task = str(task_name or "")
        active_path = self._active_pointer_path(task)
        if active_path.exists():
            backup_path = active_path.with_name(f"active_model.broken.{datetime.now().strftime('%Y%m%d%H%M%S')}.json")
            try:
                backup_path.write_text(active_path.read_text(encoding="utf-8"), encoding="utf-8")
            except Exception as exc:
                self._warn("failed to backup active model pointer %s: %s", active_path, exc)
        file_ok = write_json(active_path, {"task_name": task, "is_active": 0, "disabled_at": _now(), "disabled_reason": reason}, self.logger)
        db_ok = self._execute("UPDATE ml_model_registry SET is_active = 0 WHERE task_name = ?", (task,))
        return bool(file_ok and db_ok)

    def repair_registry(self, task_name: str | None = None) -> dict[str, Any]:
        before = self.check_registry_consistency(task_name)
        repairs: list[dict[str, Any]] = []
        for task in self._tasks_for_check(task_name):
            active_rows = self._fetch_all(
                "SELECT * FROM ml_model_registry WHERE task_name = ? AND is_active = 1 ORDER BY created_at DESC",
                (task,),
            )
            if len(active_rows) > 1:
                keep = active_rows[0]
                for row in active_rows[1:]:
                    ok = self._execute(
                        "UPDATE ml_model_registry SET is_active = 0 WHERE task_name = ? AND model_version = ?",
                        (task, str(row.get("model_version") or "")),
                    )
                    repairs.append({"task_name": task, "model_version": row.get("model_version"), "repair": "deactivate_extra_active", "ok": ok, "kept": keep.get("model_version")})
            for row in active_rows:
                version = str(row.get("model_version") or "")
                model_path = str(row.get("model_path") or self.models_root / task / version / "model.joblib")
                if not Path(model_path).exists() or not self._schema_path_for(task, version, model_path).exists():
                    ok = self._execute(
                        "UPDATE ml_model_registry SET is_active = 0 WHERE task_name = ? AND model_version = ?",
                        (task, version),
                    )
                    repairs.append({"task_name": task, "model_version": version, "repair": "deactivate_broken_db_active", "ok": ok})
            pointer_payload = read_json(self._active_pointer_path(task), self.logger)
            if pointer_payload and pointer_payload.get("is_active") != 0:
                version = str(pointer_payload.get("model_version") or "")
                model_path = str(pointer_payload.get("model_path") or self.models_root / task / version / "model.joblib")
                rows = self._fetch_all("SELECT * FROM ml_model_registry WHERE task_name = ? AND model_version = ? AND is_active = 1", (task, version))
                if not version or not Path(model_path).exists() or not self._schema_path_for(task, version, model_path).exists() or not rows:
                    ok = self.disable_active_model(task, reason="registry_repair_broken_active_pointer")
                    repairs.append({"task_name": task, "model_version": version, "repair": "disable_broken_active_pointer", "ok": ok})
        after = self.check_registry_consistency(task_name)
        return {"ok": after.get("ok", False), "before": before, "after": after, "repairs": repairs}

    def _loads(self, value: Any, default: Any) -> Any:
        if isinstance(value, str):
            try:
                return json.loads(value)
            except Exception:
                return default
        return value if value is not None else default

    def deactivate_all(self, task_name: str) -> bool:
        return self.deactivate_model(task_name)

    def rollback(self, task_name: str, model_version: str) -> bool:
        return self.rollback_to_version(task_name, model_version)
