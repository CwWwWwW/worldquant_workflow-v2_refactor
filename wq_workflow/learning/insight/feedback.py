from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, default=str)


class InsightFeedbackRecorder:
    def __init__(self, *, storage: Any | None = None, db_path: str | Path | None = None, logger: Any | None = None) -> None:
        self.storage = storage
        self.db_path = Path(db_path) if db_path is not None else getattr(getattr(storage, "config", None), "db_path", None)
        self.logger = logger

    def record_usage(self, insight_id: str, *, alpha_id: str = "", context: dict[str, Any] | None = None) -> str:
        usage_id = uuid.uuid4().hex
        self._insert("insight_usage", {"usage_id": usage_id, "insight_id": insight_id, "alpha_id": alpha_id, "context_json": _json(context or {}), "created_at": datetime.now().isoformat(timespec="seconds")})
        return usage_id

    def record_effect(self, insight_id: str, *, alpha_id: str = "", effect: dict[str, Any] | None = None) -> str:
        sample_id = uuid.uuid4().hex
        self._insert("insight_effect_samples", {"sample_id": sample_id, "insight_id": insight_id, "alpha_id": alpha_id, "effect_json": _json(effect or {}), "created_at": datetime.now().isoformat(timespec="seconds")})
        return sample_id

    def update_confidence(self, insight_id: str, confidence: float) -> dict[str, Any]:
        return {"insight_id": insight_id, "confidence": confidence, "status": "observe_only"}

    def _insert(self, table: str, values: dict[str, Any]) -> None:
        if not self.db_path:
            return
        conn = None
        try:
            from wq_workflow.storage.schema import initialize_schema
            conn = sqlite3.connect(self.db_path)
            initialize_schema(conn)
            columns = list(values)
            placeholders = ",".join("?" for _ in columns)
            conn.execute(f"INSERT INTO {table} ({','.join(columns)}) VALUES ({placeholders})", tuple(values[c] for c in columns))
            conn.commit()
        except Exception as exc:
            if self.logger:
                self.logger.debug("insight feedback insert skipped: %s", exc)
        finally:
            if conn is not None:
                conn.close()
