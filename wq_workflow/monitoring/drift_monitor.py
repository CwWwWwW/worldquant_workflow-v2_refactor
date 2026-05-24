from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any


class DriftMonitor:
    def __init__(self, *, storage: Any | None = None, config: Any | None = None, logger: Any | None = None, db_path: str | Path | None = None) -> None:
        self.storage = storage
        self.config = config
        self.logger = logger
        self.db_path = Path(db_path) if db_path is not None else getattr(getattr(storage, "config", None), "db_path", None)

    def check(self, samples: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        if not getattr(self.config, "enable_drift_monitor", False):
            return {"status": "disabled"}
        if not samples or len(samples) < int(getattr(self.config, "ml_min_samples", 200) or 200):
            return {"status": "not_enough_data", "sample_count": len(samples or [])}
        event = {"event_id": uuid.uuid4().hex, "event_type": "drift_check", "severity": "info", "payload_json": json.dumps({"sample_count": len(samples)}, ensure_ascii=False), "created_at": datetime.now().isoformat(timespec="seconds")}
        self._write_event(event)
        return {"status": "ok", "sample_count": len(samples)}

    def _write_event(self, event: dict[str, Any]) -> None:
        if not self.db_path:
            return
        conn = None
        try:
            from wq_workflow.storage.schema import initialize_schema
            conn = sqlite3.connect(self.db_path)
            initialize_schema(conn)
            conn.execute("INSERT INTO drift_events (event_id, event_type, severity, payload_json, created_at) VALUES (?, ?, ?, ?, ?)", tuple(event[k] for k in ["event_id", "event_type", "severity", "payload_json", "created_at"]))
            conn.commit()
        except Exception as exc:
            if self.logger:
                self.logger.debug("drift event skipped: %s", exc)
        finally:
            if conn is not None:
                conn.close()
