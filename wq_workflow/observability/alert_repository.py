from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from wq_workflow.data.json_utils import json_dumps_safe, json_loads_safe
from wq_workflow.data.migrations import initialize_refactor_tables

from .alert_schema import AlertEvent, AlertRule, DriftRule, DriftSignal


class AlertRepository:
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

    def save_drift_rule(self, rule: DriftRule) -> bool:
        return bool(self._safe(lambda: self._save_drift_rule(DriftRule.from_dict(rule).to_dict()), False))

    def _save_drift_rule(self, data: dict[str, Any]) -> bool:
        with self.connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO observability_drift_rules
                (rule_id, metric_name, source, rule_type, window_size, baseline_window_size, threshold, direction, severity, enabled, description, created_at, raw_payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (data["rule_id"], data["metric_name"], data.get("source"), data["rule_type"], data["window_size"], data["baseline_window_size"], data["threshold"], data["direction"], data["severity"], 1 if data.get("enabled") else 0, data.get("description"), data["created_at"], json_dumps_safe(data.get("raw_payload", {}))),
            )
            self._commit(conn)
        return True

    def list_drift_rules(self, enabled_only: bool = False) -> list[DriftRule]:
        return self._safe(lambda: self._list_drift_rules(enabled_only), []) or []

    def _list_drift_rules(self, enabled_only: bool) -> list[DriftRule]:
        sql = "SELECT * FROM observability_drift_rules"
        params: list[Any] = []
        if enabled_only:
            sql += " WHERE enabled=1"
        sql += " ORDER BY created_at DESC"
        with self.connection() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        return [_drift_rule_from_row(row) for row in rows]

    def save_drift_signal(self, signal: DriftSignal) -> bool:
        return bool(self._safe(lambda: self._save_drift_signal(DriftSignal.from_dict(signal).to_dict()), False))

    def _save_drift_signal(self, data: dict[str, Any]) -> bool:
        with self.connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO observability_drift_signals
                (signal_id, rule_id, source, metric_name, current_value_json, baseline_value_json, delta, delta_ratio, threshold, triggered, severity, reason_codes_json, created_at, raw_payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (data["signal_id"], data["rule_id"], data["source"], data["metric_name"], json_dumps_safe(data.get("current_value")), json_dumps_safe(data.get("baseline_value")), data.get("delta"), data.get("delta_ratio"), data.get("threshold"), 1 if data.get("triggered") else 0, data["severity"], json_dumps_safe(data.get("reason_codes", [])), data["created_at"], json_dumps_safe(data.get("raw_payload", {}))),
            )
            self._commit(conn)
        return True

    def list_drift_signals(self, source: str | None = None, metric_name: str | None = None, limit: int = 1000) -> list[DriftSignal]:
        return self._safe(lambda: self._list_drift_signals(source, metric_name, limit), []) or []

    def _list_drift_signals(self, source: str | None, metric_name: str | None, limit: int) -> list[DriftSignal]:
        clauses: list[str] = []
        params: list[Any] = []
        if source:
            clauses.append("source=?")
            params.append(source)
        if metric_name:
            clauses.append("metric_name=?")
            params.append(metric_name)
        sql = "SELECT * FROM observability_drift_signals"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(max(1, int(limit)))
        with self.connection() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        return [_drift_signal_from_row(row) for row in rows]

    def save_alert_rule(self, rule: AlertRule) -> bool:
        return bool(self._safe(lambda: self._save_alert_rule(AlertRule.from_dict(rule).to_dict()), False))

    def _save_alert_rule(self, data: dict[str, Any]) -> bool:
        with self.connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO observability_alert_rules
                (rule_id, alert_name, source, condition_type, metric_name, severity, enabled, threshold, description, created_at, raw_payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (data["rule_id"], data["alert_name"], data.get("source"), data["condition_type"], data.get("metric_name"), data["severity"], 1 if data.get("enabled") else 0, data.get("threshold"), data.get("description"), data["created_at"], json_dumps_safe(data.get("raw_payload", {}))),
            )
            self._commit(conn)
        return True

    def list_alert_rules(self, enabled_only: bool = False) -> list[AlertRule]:
        return self._safe(lambda: self._list_alert_rules(enabled_only), []) or []

    def _list_alert_rules(self, enabled_only: bool) -> list[AlertRule]:
        sql = "SELECT * FROM observability_alert_rules"
        if enabled_only:
            sql += " WHERE enabled=1"
        sql += " ORDER BY created_at DESC"
        with self.connection() as conn:
            rows = conn.execute(sql).fetchall()
        return [_alert_rule_from_row(row) for row in rows]

    def save_alert_event(self, event: AlertEvent) -> bool:
        return bool(self._safe(lambda: self._save_alert_event(AlertEvent.from_dict(event).to_dict()), False))

    def _save_alert_event(self, data: dict[str, Any]) -> bool:
        with self.connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO observability_alert_events
                (alert_id, rule_id, alert_name, source, severity, status, message, triggered, created_at, metric_name, metric_value_json, reason_codes_json, raw_payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (data["alert_id"], data["rule_id"], data["alert_name"], data["source"], data["severity"], data["status"], data["message"], 1 if data.get("triggered") else 0, data["created_at"], data.get("metric_name"), json_dumps_safe(data.get("metric_value")), json_dumps_safe(data.get("reason_codes", [])), json_dumps_safe(data.get("raw_payload", {}))),
            )
            self._commit(conn)
        return True

    def list_alert_events(self, source: str | None = None, severity: str | None = None, limit: int = 1000) -> list[AlertEvent]:
        return self._safe(lambda: self._list_alert_events(source, severity, limit), []) or []

    def _list_alert_events(self, source: str | None, severity: str | None, limit: int) -> list[AlertEvent]:
        clauses: list[str] = []
        params: list[Any] = []
        if source:
            clauses.append("source=?")
            params.append(source)
        if severity:
            clauses.append("severity=?")
            params.append(severity)
        sql = "SELECT * FROM observability_alert_events"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(max(1, int(limit)))
        with self.connection() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        return [_alert_event_from_row(row) for row in rows]

    def _safe(self, func: Any, default: Any) -> Any:
        try:
            return func()
        except Exception as exc:
            self.last_error = str(exc)
            try:
                if self.logger is not None:
                    self.logger.warning("observability alert repository operation failed: %s", exc)
            except Exception:
                pass
            return default

    def _commit(self, conn: sqlite3.Connection) -> None:
        try:
            conn.commit()
        except Exception:
            pass


def _drift_rule_from_row(row: sqlite3.Row) -> DriftRule:
    return DriftRule.from_dict({
        "rule_id": row["rule_id"],
        "metric_name": row["metric_name"],
        "source": row["source"],
        "rule_type": row["rule_type"],
        "window_size": row["window_size"],
        "baseline_window_size": row["baseline_window_size"],
        "threshold": row["threshold"],
        "direction": row["direction"],
        "severity": row["severity"],
        "enabled": bool(row["enabled"]),
        "description": row["description"],
        "created_at": row["created_at"],
        "raw_payload": json_loads_safe(row["raw_payload"], {}),
    })


def _drift_signal_from_row(row: sqlite3.Row) -> DriftSignal:
    return DriftSignal.from_dict({
        "signal_id": row["signal_id"],
        "rule_id": row["rule_id"],
        "source": row["source"],
        "metric_name": row["metric_name"],
        "current_value": json_loads_safe(row["current_value_json"], None),
        "baseline_value": json_loads_safe(row["baseline_value_json"], None),
        "delta": row["delta"],
        "delta_ratio": row["delta_ratio"],
        "threshold": row["threshold"],
        "triggered": bool(row["triggered"]),
        "severity": row["severity"],
        "reason_codes": json_loads_safe(row["reason_codes_json"], []),
        "created_at": row["created_at"],
        "raw_payload": json_loads_safe(row["raw_payload"], {}),
    })


def _alert_rule_from_row(row: sqlite3.Row) -> AlertRule:
    return AlertRule.from_dict({
        "rule_id": row["rule_id"],
        "alert_name": row["alert_name"],
        "source": row["source"],
        "condition_type": row["condition_type"],
        "metric_name": row["metric_name"],
        "severity": row["severity"],
        "enabled": bool(row["enabled"]),
        "threshold": row["threshold"],
        "description": row["description"],
        "created_at": row["created_at"],
        "raw_payload": json_loads_safe(row["raw_payload"], {}),
    })


def _alert_event_from_row(row: sqlite3.Row) -> AlertEvent:
    return AlertEvent.from_dict({
        "alert_id": row["alert_id"],
        "rule_id": row["rule_id"],
        "alert_name": row["alert_name"],
        "source": row["source"],
        "severity": row["severity"],
        "status": row["status"],
        "message": row["message"],
        "triggered": bool(row["triggered"]),
        "created_at": row["created_at"],
        "metric_name": row["metric_name"],
        "metric_value": json_loads_safe(row["metric_value_json"], None),
        "reason_codes": json_loads_safe(row["reason_codes_json"], []),
        "raw_payload": json_loads_safe(row["raw_payload"], {}),
    })
