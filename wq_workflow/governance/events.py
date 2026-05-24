from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

EVENT_TYPES = {
    "model_expired", "model_prediction_error", "model_load_error", "registry_inconsistent", "schema_mismatch",
    "online_performance_drop", "drift_detected", "sample_pollution_detected", "auto_retrain_started",
    "auto_retrain_failed", "auto_retrain_succeeded", "model_disabled", "model_rolled_back", "fallback_to_legacy",
    "promotion_blocked", "promotion_approved", "model_degraded", "model_weight_reduced", "hard_decision_disabled",
    "hard_decision_allowed", "model_shadow_only", "governance_check_failed", "governance_action_failed",
    "governance_startup_check",
}

DDL = """
CREATE TABLE IF NOT EXISTS ml_model_events (
    event_id TEXT PRIMARY KEY,
    task_name TEXT,
    model_version TEXT,
    event_type TEXT,
    severity TEXT,
    message TEXT,
    action_taken TEXT,
    raw_payload TEXT,
    created_at TEXT
);
"""


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def json_safe(value: Any) -> Any:
    try:
        from wq_workflow.data.json_utils import to_jsonable
        return to_jsonable(value)
    except Exception:
        pass
    try:
        json.dumps(value, ensure_ascii=False, allow_nan=False, default=str)
        return value
    except Exception:
        return str(value)


def json_dumps_safe(value: Any) -> str:
    return json.dumps(json_safe(value), ensure_ascii=False, allow_nan=False, default=str)


class ModelEventLogger:
    def __init__(self, conn: sqlite3.Connection | None = None, db_path: str | Path | None = None, logger: Any | None = None) -> None:
        self.conn = conn
        self.db_path = Path(db_path) if db_path is not None else None
        self.logger = logger

    def _warn(self, message: str, *args: Any) -> None:
        try:
            if self.logger is not None:
                self.logger.warning(message, *args)
        except Exception:
            pass

    def _connect(self) -> sqlite3.Connection | None:
        if self.conn is not None:
            return self.conn
        if self.db_path is None:
            return None
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        return sqlite3.connect(self.db_path)

    def record(
        self,
        *,
        task_name: str = "",
        model_version: str | None = None,
        event_type: str = "governance_check_failed",
        severity: str = "info",
        message: str = "",
        action_taken: str = "",
        raw_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        event = {
            "event_id": uuid.uuid4().hex,
            "task_name": str(task_name or ""),
            "model_version": model_version,
            "event_type": str(event_type or "governance_check_failed"),
            "severity": str(severity or "info"),
            "message": str(message or ""),
            "action_taken": str(action_taken or ""),
            "raw_payload": raw_payload or {},
            "created_at": utc_now_iso(),
        }
        conn = None
        close = False
        try:
            conn = self._connect()
            if conn is None:
                return event
            close = self.conn is None
            conn.execute(DDL)
            conn.execute(
                """
                INSERT INTO ml_model_events
                (event_id, task_name, model_version, event_type, severity, message, action_taken, raw_payload, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (event["event_id"], event["task_name"], event["model_version"], event["event_type"], event["severity"], event["message"], event["action_taken"], json_dumps_safe(event["raw_payload"]), event["created_at"]),
            )
            conn.commit()
        except Exception as exc:
            self._warn("governance event write failed: %s", exc)
        finally:
            if close and conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass
        return event
