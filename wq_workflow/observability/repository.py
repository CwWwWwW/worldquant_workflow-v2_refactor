from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from wq_workflow.data.json_utils import json_dumps_safe, json_loads_safe
from wq_workflow.data.migrations import initialize_refactor_tables

from .schema import ObservabilityMetric, ObservabilitySnapshot, ObservabilitySourceStatus, ObservabilitySummary


class ObservabilityRepository:
    def __init__(self, conn: sqlite3.Connection | None = None, *, storage: Any | None = None, db_path: str | Path | None = None, logger: Any | None = None) -> None:
        self.conn = conn
        self.storage = storage
        path = db_path if db_path is not None else getattr(getattr(storage, "config", None), "db_path", None)
        self.db_path = Path(path) if path is not None else None
        self.logger = logger
        self.last_error = ""

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        if self.conn is not None:
            self.conn.row_factory = sqlite3.Row
            initialize_refactor_tables(self.conn)
            yield self.conn
            return
        if self.db_path is None:
            raise RuntimeError("database path unavailable")
        from wq_workflow.storage.schema import initialize_schema
        from wq_workflow.storage.sqlite_store import connect_db

        conn = connect_db(self.db_path)
        try:
            initialize_schema(conn)
            initialize_refactor_tables(conn)
            yield conn
        finally:
            conn.close()

    def initialize(self) -> dict[str, Any]:
        return self._safe(lambda: self._initialize(), {"ok": False})

    def _initialize(self) -> dict[str, Any]:
        with self.connection() as conn:
            initialize_refactor_tables(conn)
            self._commit(conn)
        return {"ok": True}

    def save_metric(self, metric: ObservabilityMetric) -> bool:
        return bool(self._safe(lambda: self._save_metric(ObservabilityMetric.from_dict(metric).to_dict()), False))

    def save_metrics(self, metrics: list[ObservabilityMetric]) -> bool:
        ok = True
        for metric in metrics or []:
            ok = self.save_metric(metric) and ok
        return ok

    def _save_metric(self, data: dict[str, Any]) -> bool:
        with self.connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO observability_metrics
                (metric_id, source, metric_name, metric_type, value_json, unit, timestamp, tags_json, raw_payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (data["metric_id"], data["source"], data["metric_name"], data["metric_type"], json_dumps_safe(data.get("value")), data.get("unit"), data["timestamp"], json_dumps_safe(data.get("tags", {})), json_dumps_safe(data.get("raw_payload", {}))),
            )
            self._commit(conn)
        return True

    def list_metrics(self, source: str | None = None, metric_name: str | None = None, limit: int = 1000) -> list[ObservabilityMetric]:
        return self._safe(lambda: self._list_metrics(source, metric_name, limit), []) or []

    def _list_metrics(self, source: str | None, metric_name: str | None, limit: int) -> list[ObservabilityMetric]:
        clauses: list[str] = []
        params: list[Any] = []
        if source:
            clauses.append("source=?")
            params.append(source)
        if metric_name:
            clauses.append("metric_name=?")
            params.append(metric_name)
        sql = "SELECT * FROM observability_metrics"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY timestamp DESC LIMIT ?"
        params.append(max(1, int(limit)))
        with self.connection() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        return [_metric_from_row(row) for row in rows]

    def save_source_status(self, status: ObservabilitySourceStatus) -> bool:
        return bool(self._safe(lambda: self._save_source_status(ObservabilitySourceStatus.from_dict(status).to_dict()), False))

    def _save_source_status(self, data: dict[str, Any]) -> bool:
        with self.connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO observability_source_status
                (source, available, status_path, table_names_json, last_updated_at, is_stale, metric_count, warnings_json, raw_payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (data["source"], 1 if data.get("available") else 0, data.get("status_path"), json_dumps_safe(data.get("table_names", [])), data.get("last_updated_at"), 1 if data.get("is_stale") else 0, int(data.get("metric_count") or 0), json_dumps_safe(data.get("warnings", [])), json_dumps_safe(data.get("raw_payload", {}))),
            )
            self._commit(conn)
        return True

    def list_source_statuses(self) -> list[ObservabilitySourceStatus]:
        return self._safe(lambda: self._list_source_statuses(), []) or []

    def _list_source_statuses(self) -> list[ObservabilitySourceStatus]:
        with self.connection() as conn:
            rows = conn.execute("SELECT * FROM observability_source_status ORDER BY source").fetchall()
        return [_source_status_from_row(row) for row in rows]

    def save_snapshot(self, snapshot: ObservabilitySnapshot) -> bool:
        return bool(self._safe(lambda: self._save_snapshot(ObservabilitySnapshot.from_dict(snapshot).to_dict()), False))

    def _save_snapshot(self, data: dict[str, Any]) -> bool:
        with self.connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO observability_snapshots
                (snapshot_id, generated_at, metrics_json, source_statuses_json, summary_json, warnings_json, raw_payload)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (data["snapshot_id"], data["generated_at"], json_dumps_safe(data.get("metrics", [])), json_dumps_safe(data.get("source_statuses", [])), json_dumps_safe(data.get("summary", {})), json_dumps_safe(data.get("warnings", [])), json_dumps_safe(data.get("raw_payload", {}))),
            )
            self._commit(conn)
        return True

    def get_latest_snapshot(self) -> ObservabilitySnapshot | None:
        return self._safe(lambda: self._get_latest_snapshot(), None)

    def _get_latest_snapshot(self) -> ObservabilitySnapshot | None:
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM observability_snapshots ORDER BY generated_at DESC LIMIT 1").fetchone()
        return _snapshot_from_row(row) if row else None

    def list_snapshots(self, limit: int = 20) -> list[ObservabilitySnapshot]:
        return self._safe(lambda: self._list_snapshots(limit), []) or []

    def _list_snapshots(self, limit: int) -> list[ObservabilitySnapshot]:
        with self.connection() as conn:
            rows = conn.execute("SELECT * FROM observability_snapshots ORDER BY generated_at DESC LIMIT ?", (max(1, int(limit)),)).fetchall()
        return [_snapshot_from_row(row) for row in rows if row is not None]

    def save_summary(self, summary: ObservabilitySummary) -> bool:
        return bool(self._safe(lambda: self._save_summary(ObservabilitySummary.from_dict(summary).to_dict()), False))

    def _save_summary(self, data: dict[str, Any]) -> bool:
        with self.connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO observability_summaries
                (summary_id, generated_at, total_metrics, available_sources, stale_sources, warning_count,
                 workflow_summary_json, ml_summary_json, governance_summary_json, experiment_summary_json,
                 offline_summary_json, strategy_summary_json, system_summary_json, warnings_json, raw_payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (data["summary_id"], data["generated_at"], data["total_metrics"], data["available_sources"], data["stale_sources"], data["warning_count"], json_dumps_safe(data.get("workflow_summary", {})), json_dumps_safe(data.get("ml_summary", {})), json_dumps_safe(data.get("governance_summary", {})), json_dumps_safe(data.get("experiment_summary", {})), json_dumps_safe(data.get("offline_summary", {})), json_dumps_safe(data.get("strategy_summary", {})), json_dumps_safe(data.get("system_summary", {})), json_dumps_safe(data.get("warnings", [])), json_dumps_safe(data.get("raw_payload", {}))),
            )
            self._commit(conn)
        return True

    def get_latest_summary(self) -> ObservabilitySummary | None:
        return self._safe(lambda: self._get_latest_summary(), None)

    def _get_latest_summary(self) -> ObservabilitySummary | None:
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM observability_summaries ORDER BY generated_at DESC LIMIT 1").fetchone()
        return _summary_from_row(row) if row else None

    def _safe(self, func: Any, default: Any) -> Any:
        try:
            return func()
        except Exception as exc:
            self.last_error = str(exc)
            try:
                if self.logger is not None:
                    self.logger.warning("observability repository operation failed: %s", exc)
            except Exception:
                pass
            return default

    def _commit(self, conn: sqlite3.Connection) -> None:
        try:
            conn.commit()
        except Exception:
            pass


def _metric_from_row(row: sqlite3.Row) -> ObservabilityMetric:
    return ObservabilityMetric.from_dict({
        "metric_id": row["metric_id"],
        "source": row["source"],
        "metric_name": row["metric_name"],
        "metric_type": row["metric_type"],
        "value": json_loads_safe(row["value_json"], None),
        "unit": row["unit"],
        "timestamp": row["timestamp"],
        "tags": json_loads_safe(row["tags_json"], {}),
        "raw_payload": json_loads_safe(row["raw_payload"], {}),
    })


def _source_status_from_row(row: sqlite3.Row) -> ObservabilitySourceStatus:
    return ObservabilitySourceStatus.from_dict({
        "source": row["source"],
        "available": bool(row["available"]),
        "status_path": row["status_path"],
        "table_names": json_loads_safe(row["table_names_json"], []),
        "last_updated_at": row["last_updated_at"],
        "is_stale": bool(row["is_stale"]),
        "metric_count": row["metric_count"],
        "warnings": json_loads_safe(row["warnings_json"], []),
        "raw_payload": json_loads_safe(row["raw_payload"], {}),
    })


def _snapshot_from_row(row: sqlite3.Row) -> ObservabilitySnapshot:
    return ObservabilitySnapshot.from_dict({
        "snapshot_id": row["snapshot_id"],
        "generated_at": row["generated_at"],
        "metrics": json_loads_safe(row["metrics_json"], []),
        "source_statuses": json_loads_safe(row["source_statuses_json"], []),
        "summary": json_loads_safe(row["summary_json"], {}),
        "warnings": json_loads_safe(row["warnings_json"], []),
        "raw_payload": json_loads_safe(row["raw_payload"], {}),
    })


def _summary_from_row(row: sqlite3.Row) -> ObservabilitySummary:
    return ObservabilitySummary.from_dict({
        "summary_id": row["summary_id"],
        "generated_at": row["generated_at"],
        "total_metrics": row["total_metrics"],
        "available_sources": row["available_sources"],
        "stale_sources": row["stale_sources"],
        "warning_count": row["warning_count"],
        "workflow_summary": json_loads_safe(row["workflow_summary_json"], {}),
        "ml_summary": json_loads_safe(row["ml_summary_json"], {}),
        "governance_summary": json_loads_safe(row["governance_summary_json"], {}),
        "experiment_summary": json_loads_safe(row["experiment_summary_json"], {}),
        "offline_summary": json_loads_safe(row["offline_summary_json"], {}),
        "strategy_summary": json_loads_safe(row["strategy_summary_json"], {}),
        "system_summary": json_loads_safe(row["system_summary_json"], {}),
        "warnings": json_loads_safe(row["warnings_json"], []),
        "raw_payload": json_loads_safe(row["raw_payload"], {}),
    })
