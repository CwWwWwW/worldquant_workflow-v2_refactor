from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from wq_workflow.data.json_utils import json_dumps_safe, json_loads_safe
from wq_workflow.data.migrations import initialize_refactor_tables

from .explanation_schema import DailyRunReport, DecisionTrace, ExplanationEvidence, RunExplanation, StageSummaryReport


class ExplanationRepository:
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

    def save_evidence(self, evidence: ExplanationEvidence) -> bool:
        return bool(self._safe(lambda: self._save_evidence(ExplanationEvidence.from_dict(evidence).to_dict()), False))

    def save_evidence_batch(self, evidence: list[ExplanationEvidence]) -> bool:
        ok = True
        for item in list(evidence or []):
            ok = self.save_evidence(item) and ok
        return ok

    def _save_evidence(self, data: dict[str, Any]) -> bool:
        with self.connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO observability_explanation_evidence
                (evidence_id, source, evidence_type, title, summary, confidence, observed, estimated, advisory, timestamp,
                 related_ids_json, reason_codes_json, risk_flags_json, raw_payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (data["evidence_id"], data["source"], data["evidence_type"], data["title"], data["summary"], data["confidence"], 1 if data.get("observed") else 0, 1 if data.get("estimated") else 0, 1 if data.get("advisory") else 0, data["timestamp"], json_dumps_safe(data.get("related_ids", [])), json_dumps_safe(data.get("reason_codes", [])), json_dumps_safe(data.get("risk_flags", [])), json_dumps_safe(data.get("raw_payload", {}))),
            )
            self._commit(conn)
        return True

    def list_evidence(self, source: str | None = None, evidence_type: str | None = None, limit: int = 1000) -> list[ExplanationEvidence]:
        return self._safe(lambda: self._list_evidence(source, evidence_type, limit), []) or []

    def _list_evidence(self, source: str | None, evidence_type: str | None, limit: int) -> list[ExplanationEvidence]:
        clauses: list[str] = []
        params: list[Any] = []
        if source:
            clauses.append("source=?")
            params.append(source)
        if evidence_type:
            clauses.append("evidence_type=?")
            params.append(evidence_type)
        sql = "SELECT * FROM observability_explanation_evidence"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY timestamp DESC LIMIT ?"
        params.append(max(1, int(limit)))
        with self.connection() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        return [_evidence_from_row(row) for row in rows]

    def save_trace(self, trace: DecisionTrace) -> bool:
        return bool(self._safe(lambda: self._save_trace(DecisionTrace.from_dict(trace).to_dict()), False))

    def _save_trace(self, data: dict[str, Any]) -> bool:
        with self.connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO observability_decision_traces
                (trace_id, generated_at, decision_id, alpha_id, run_id, strategy_id, decision_type, decision_summary,
                 selected_action, alternative_actions_json, evidence_json, explanation, confidence, warnings_json, raw_payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (data["trace_id"], data["generated_at"], data.get("decision_id"), data.get("alpha_id"), data.get("run_id"), data.get("strategy_id"), data["decision_type"], data.get("decision_summary"), data.get("selected_action"), json_dumps_safe(data.get("alternative_actions", [])), json_dumps_safe(data.get("evidence", [])), data.get("explanation"), data.get("confidence"), json_dumps_safe(data.get("warnings", [])), json_dumps_safe(data.get("raw_payload", {}))),
            )
            self._commit(conn)
        return True

    def list_traces(self, decision_type: str | None = None, limit: int = 1000) -> list[DecisionTrace]:
        return self._safe(lambda: self._list_traces(decision_type, limit), []) or []

    def _list_traces(self, decision_type: str | None, limit: int) -> list[DecisionTrace]:
        sql = "SELECT * FROM observability_decision_traces"
        params: list[Any] = []
        if decision_type:
            sql += " WHERE decision_type=?"
            params.append(decision_type)
        sql += " ORDER BY generated_at DESC LIMIT ?"
        params.append(max(1, int(limit)))
        with self.connection() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        return [_trace_from_row(row) for row in rows]

    def save_run_explanation(self, explanation: RunExplanation) -> bool:
        return bool(self._safe(lambda: self._save_run_explanation(RunExplanation.from_dict(explanation).to_dict()), False))

    def _save_run_explanation(self, data: dict[str, Any]) -> bool:
        with self.connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO observability_run_explanations
                (explanation_id, generated_at, window_start, window_end, run_summary, key_findings_json,
                 decision_traces_json, alerts_summary_json, diagnosis_summary_json, strategy_summary_json, budget_summary_json,
                 evidence_summary_json, limitations_json, recommended_human_checks_json, auto_action_allowed, raw_payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (data["explanation_id"], data["generated_at"], data.get("window_start"), data.get("window_end"), data.get("run_summary"), json_dumps_safe(data.get("key_findings", [])), json_dumps_safe(data.get("decision_traces", [])), json_dumps_safe(data.get("alerts_summary", {})), json_dumps_safe(data.get("diagnosis_summary", {})), json_dumps_safe(data.get("strategy_summary", {})), json_dumps_safe(data.get("budget_summary", {})), json_dumps_safe(data.get("evidence_summary", {})), json_dumps_safe(data.get("limitations", [])), json_dumps_safe(data.get("recommended_human_checks", [])), 0, json_dumps_safe(data.get("raw_payload", {}))),
            )
            self._commit(conn)
        return True

    def get_latest_run_explanation(self) -> RunExplanation | None:
        return self._safe(lambda: self._get_latest_run_explanation(), None)

    def _get_latest_run_explanation(self) -> RunExplanation | None:
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM observability_run_explanations ORDER BY generated_at DESC LIMIT 1").fetchone()
        return _run_from_row(row) if row else None

    def save_daily_report(self, report: DailyRunReport) -> bool:
        return bool(self._safe(lambda: self._save_daily_report(DailyRunReport.from_dict(report).to_dict()), False))

    def _save_daily_report(self, data: dict[str, Any]) -> bool:
        with self.connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO observability_daily_reports
                (report_id, generated_at, date, overall_summary, health_status, key_metrics_json, key_alerts_json,
                 key_diagnoses_json, strategy_explanations_json, budget_explanations_json, offline_evidence_summary_json,
                 counterfactual_limitations_json, recommended_human_checks_json, auto_action_allowed, raw_payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (data["report_id"], data["generated_at"], data["date"], data.get("overall_summary"), data.get("health_status"), json_dumps_safe(data.get("key_metrics", {})), json_dumps_safe(data.get("key_alerts", [])), json_dumps_safe(data.get("key_diagnoses", [])), json_dumps_safe(data.get("strategy_explanations", [])), json_dumps_safe(data.get("budget_explanations", [])), json_dumps_safe(data.get("offline_evidence_summary", {})), json_dumps_safe(data.get("counterfactual_limitations", [])), json_dumps_safe(data.get("recommended_human_checks", [])), 0, json_dumps_safe(data.get("raw_payload", {}))),
            )
            self._commit(conn)
        return True

    def get_latest_daily_report(self) -> DailyRunReport | None:
        return self._safe(lambda: self._get_latest_daily_report(), None)

    def _get_latest_daily_report(self) -> DailyRunReport | None:
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM observability_daily_reports ORDER BY generated_at DESC LIMIT 1").fetchone()
        return _daily_from_row(row) if row else None

    def save_stage_summary(self, report: StageSummaryReport) -> bool:
        return bool(self._safe(lambda: self._save_stage_summary(StageSummaryReport.from_dict(report).to_dict()), False))

    def _save_stage_summary(self, data: dict[str, Any]) -> bool:
        with self.connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO observability_stage_reports
                (report_id, generated_at, stage_name, summary, completed_substages_json, generated_reports_json,
                 key_capabilities_json, known_limitations_json, next_stage_recommendations_json, auto_action_allowed, raw_payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (data["report_id"], data["generated_at"], data.get("stage_name"), data.get("summary"), json_dumps_safe(data.get("completed_substages", [])), json_dumps_safe(data.get("generated_reports", [])), json_dumps_safe(data.get("key_capabilities", [])), json_dumps_safe(data.get("known_limitations", [])), json_dumps_safe(data.get("next_stage_recommendations", [])), 0, json_dumps_safe(data.get("raw_payload", {}))),
            )
            self._commit(conn)
        return True

    def get_latest_stage_summary(self) -> StageSummaryReport | None:
        return self._safe(lambda: self._get_latest_stage_summary(), None)

    def _get_latest_stage_summary(self) -> StageSummaryReport | None:
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM observability_stage_reports ORDER BY generated_at DESC LIMIT 1").fetchone()
        return _stage_from_row(row) if row else None

    def _safe(self, func: Any, default: Any) -> Any:
        try:
            return func()
        except Exception as exc:
            self.last_error = str(exc)
            try:
                if self.logger is not None:
                    self.logger.warning("explanation repository operation failed: %s", exc)
            except Exception:
                pass
            return default

    def _commit(self, conn: sqlite3.Connection) -> None:
        try:
            conn.commit()
        except Exception:
            pass


def _evidence_from_row(row: sqlite3.Row) -> ExplanationEvidence:
    return ExplanationEvidence.from_dict({
        "evidence_id": row["evidence_id"], "source": row["source"], "evidence_type": row["evidence_type"], "title": row["title"], "summary": row["summary"], "confidence": row["confidence"], "observed": bool(row["observed"]), "estimated": bool(row["estimated"]), "advisory": bool(row["advisory"]), "timestamp": row["timestamp"], "related_ids": json_loads_safe(row["related_ids_json"], []), "reason_codes": json_loads_safe(row["reason_codes_json"], []), "risk_flags": json_loads_safe(row["risk_flags_json"], []), "raw_payload": json_loads_safe(row["raw_payload"], {}),
    })


def _trace_from_row(row: sqlite3.Row) -> DecisionTrace:
    return DecisionTrace.from_dict({
        "trace_id": row["trace_id"], "generated_at": row["generated_at"], "decision_id": row["decision_id"], "alpha_id": row["alpha_id"], "run_id": row["run_id"], "strategy_id": row["strategy_id"], "decision_type": row["decision_type"], "decision_summary": row["decision_summary"], "selected_action": row["selected_action"], "alternative_actions": json_loads_safe(row["alternative_actions_json"], []), "evidence": json_loads_safe(row["evidence_json"], []), "explanation": row["explanation"], "confidence": row["confidence"], "warnings": json_loads_safe(row["warnings_json"], []), "raw_payload": json_loads_safe(row["raw_payload"], {}),
    })


def _run_from_row(row: sqlite3.Row) -> RunExplanation:
    return RunExplanation.from_dict({
        "explanation_id": row["explanation_id"], "generated_at": row["generated_at"], "window_start": row["window_start"], "window_end": row["window_end"], "run_summary": row["run_summary"], "key_findings": json_loads_safe(row["key_findings_json"], []), "decision_traces": json_loads_safe(row["decision_traces_json"], []), "alerts_summary": json_loads_safe(row["alerts_summary_json"], {}), "diagnosis_summary": json_loads_safe(row["diagnosis_summary_json"], {}), "strategy_summary": json_loads_safe(row["strategy_summary_json"], {}), "budget_summary": json_loads_safe(row["budget_summary_json"], {}), "evidence_summary": json_loads_safe(row["evidence_summary_json"], {}), "limitations": json_loads_safe(row["limitations_json"], []), "recommended_human_checks": json_loads_safe(row["recommended_human_checks_json"], []), "auto_action_allowed": False, "raw_payload": json_loads_safe(row["raw_payload"], {}),
    })


def _daily_from_row(row: sqlite3.Row) -> DailyRunReport:
    return DailyRunReport.from_dict({
        "report_id": row["report_id"], "generated_at": row["generated_at"], "date": row["date"], "overall_summary": row["overall_summary"], "health_status": row["health_status"], "key_metrics": json_loads_safe(row["key_metrics_json"], {}), "key_alerts": json_loads_safe(row["key_alerts_json"], []), "key_diagnoses": json_loads_safe(row["key_diagnoses_json"], []), "strategy_explanations": json_loads_safe(row["strategy_explanations_json"], []), "budget_explanations": json_loads_safe(row["budget_explanations_json"], []), "offline_evidence_summary": json_loads_safe(row["offline_evidence_summary_json"], {}), "counterfactual_limitations": json_loads_safe(row["counterfactual_limitations_json"], []), "recommended_human_checks": json_loads_safe(row["recommended_human_checks_json"], []), "auto_action_allowed": False, "raw_payload": json_loads_safe(row["raw_payload"], {}),
    })


def _stage_from_row(row: sqlite3.Row) -> StageSummaryReport:
    return StageSummaryReport.from_dict({
        "report_id": row["report_id"], "generated_at": row["generated_at"], "stage_name": row["stage_name"], "summary": row["summary"], "completed_substages": json_loads_safe(row["completed_substages_json"], []), "generated_reports": json_loads_safe(row["generated_reports_json"], []), "key_capabilities": json_loads_safe(row["key_capabilities_json"], []), "known_limitations": json_loads_safe(row["known_limitations_json"], []), "next_stage_recommendations": json_loads_safe(row["next_stage_recommendations_json"], []), "auto_action_allowed": False, "raw_payload": json_loads_safe(row["raw_payload"], {}),
    })
