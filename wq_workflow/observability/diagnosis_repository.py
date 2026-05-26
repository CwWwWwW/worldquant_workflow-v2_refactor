from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from wq_workflow.data.json_utils import json_dumps_safe, json_loads_safe
from wq_workflow.data.migrations import initialize_refactor_tables

from .alert_schema import AlertEvent, DriftSignal, HealthDiagnosis, HealthDiagnosisReport


class DiagnosisRepository:
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

    def save_diagnosis(self, diagnosis: HealthDiagnosis) -> bool:
        return bool(self._safe(lambda: self._save_diagnosis(HealthDiagnosis.from_dict(diagnosis).to_dict()), False))

    def _save_diagnosis(self, data: dict[str, Any]) -> bool:
        with self.connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO observability_health_diagnoses
                (diagnosis_id, area, status, severity, summary, evidence_metrics_json, alert_ids_json, drift_signal_ids_json, recommended_action, auto_action_allowed, created_at, raw_payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (data["diagnosis_id"], data["area"], data["status"], data["severity"], data["summary"], json_dumps_safe(data.get("evidence_metrics", [])), json_dumps_safe(data.get("alert_ids", [])), json_dumps_safe(data.get("drift_signal_ids", [])), data["recommended_action"], 0, data["created_at"], json_dumps_safe(data.get("raw_payload", {}))),
            )
            self._commit(conn)
        return True

    def list_diagnoses(self, area: str | None = None, status: str | None = None, limit: int = 1000) -> list[HealthDiagnosis]:
        return self._safe(lambda: self._list_diagnoses(area, status, limit), []) or []

    def _list_diagnoses(self, area: str | None, status: str | None, limit: int) -> list[HealthDiagnosis]:
        clauses: list[str] = []
        params: list[Any] = []
        if area:
            clauses.append("area=?")
            params.append(area)
        if status:
            clauses.append("status=?")
            params.append(status)
        sql = "SELECT * FROM observability_health_diagnoses"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(max(1, int(limit)))
        with self.connection() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        return [_diagnosis_from_row(row) for row in rows]

    def save_report(self, report: HealthDiagnosisReport) -> bool:
        return bool(self._safe(lambda: self._save_report(HealthDiagnosisReport.from_dict(report).to_dict()), False))

    def _save_report(self, data: dict[str, Any]) -> bool:
        with self.connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO observability_health_reports
                (report_id, generated_at, mode, overall_status, diagnoses_json, alert_events_json, drift_signals_json, summary_json, warnings_json, raw_payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (data["report_id"], data["generated_at"], "advisory", data["overall_status"], json_dumps_safe(data.get("diagnoses", [])), json_dumps_safe(data.get("alert_events", [])), json_dumps_safe(data.get("drift_signals", [])), json_dumps_safe(data.get("summary", {})), json_dumps_safe(data.get("warnings", [])), json_dumps_safe(data.get("raw_payload", {}))),
            )
            self._commit(conn)
        return True

    def get_latest_report(self) -> HealthDiagnosisReport | None:
        return self._safe(lambda: self._get_latest_report(), None)

    def _get_latest_report(self) -> HealthDiagnosisReport | None:
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM observability_health_reports ORDER BY generated_at DESC LIMIT 1").fetchone()
        return _report_from_row(row) if row else None

    def list_reports(self, limit: int = 20) -> list[HealthDiagnosisReport]:
        return self._safe(lambda: self._list_reports(limit), []) or []

    def _list_reports(self, limit: int) -> list[HealthDiagnosisReport]:
        with self.connection() as conn:
            rows = conn.execute("SELECT * FROM observability_health_reports ORDER BY generated_at DESC LIMIT ?", (max(1, int(limit)),)).fetchall()
        return [_report_from_row(row) for row in rows]

    def _safe(self, func: Any, default: Any) -> Any:
        try:
            return func()
        except Exception as exc:
            self.last_error = str(exc)
            try:
                if self.logger is not None:
                    self.logger.warning("observability diagnosis repository operation failed: %s", exc)
            except Exception:
                pass
            return default

    def _commit(self, conn: sqlite3.Connection) -> None:
        try:
            conn.commit()
        except Exception:
            pass


def _diagnosis_from_row(row: sqlite3.Row) -> HealthDiagnosis:
    return HealthDiagnosis.from_dict({
        "diagnosis_id": row["diagnosis_id"],
        "area": row["area"],
        "status": row["status"],
        "severity": row["severity"],
        "summary": row["summary"],
        "evidence_metrics": json_loads_safe(row["evidence_metrics_json"], []),
        "alert_ids": json_loads_safe(row["alert_ids_json"], []),
        "drift_signal_ids": json_loads_safe(row["drift_signal_ids_json"], []),
        "recommended_action": row["recommended_action"],
        "auto_action_allowed": False,
        "created_at": row["created_at"],
        "raw_payload": json_loads_safe(row["raw_payload"], {}),
    })


def _report_from_row(row: sqlite3.Row) -> HealthDiagnosisReport:
    return HealthDiagnosisReport.from_dict({
        "report_id": row["report_id"],
        "generated_at": row["generated_at"],
        "mode": "advisory",
        "overall_status": row["overall_status"],
        "diagnoses": json_loads_safe(row["diagnoses_json"], []),
        "alert_events": [AlertEvent.from_dict(item).to_dict() for item in json_loads_safe(row["alert_events_json"], [])],
        "drift_signals": [DriftSignal.from_dict(item).to_dict() for item in json_loads_safe(row["drift_signals_json"], [])],
        "summary": json_loads_safe(row["summary_json"], {}),
        "warnings": json_loads_safe(row["warnings_json"], []),
        "raw_payload": json_loads_safe(row["raw_payload"], {}),
    })
