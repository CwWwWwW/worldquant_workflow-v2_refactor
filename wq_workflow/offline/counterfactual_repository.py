from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from wq_workflow.data.json_utils import json_dumps_safe, json_loads_safe
from wq_workflow.data.migrations import initialize_refactor_tables
from wq_workflow.storage.sqlite_store import connect_db

from .schema import CounterfactualEstimate, CounterfactualEvidence, CounterfactualRequest, CounterfactualSummary, DecisionAction, utc_now_iso


class CounterfactualRepository:
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
            raise RuntimeError("counterfactual database path unavailable")
        conn = connect_db(self.db_path)
        try:
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

    def save_request(self, request: CounterfactualRequest) -> dict[str, Any]:
        return self._safe(lambda: self._save_request(request), {"ok": False, "request_id": getattr(request, "request_id", "")})

    def _save_request(self, request: CounterfactualRequest) -> dict[str, Any]:
        item = CounterfactualRequest.from_dict(request)
        data = item.to_dict()
        with self.connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO counterfactual_requests
                (request_id, replay_run_id, policy_decision_id, decision_id, decision_type, target_action_json,
                 actual_action_json, alpha_id, experiment_id, arm_id, budget_plan_id, features_json, context_json,
                 min_evidence, created_at, raw_payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.request_id,
                    item.replay_run_id,
                    item.policy_decision_id,
                    item.decision_id,
                    item.decision_type,
                    json_dumps_safe(data.get("target_action")) if data.get("target_action") is not None else None,
                    json_dumps_safe(data.get("actual_action")) if data.get("actual_action") is not None else None,
                    item.alpha_id,
                    item.experiment_id,
                    item.arm_id,
                    item.budget_plan_id,
                    json_dumps_safe(data.get("features") or {}),
                    json_dumps_safe(data.get("context") or {}),
                    item.min_evidence,
                    item.created_at,
                    json_dumps_safe(data.get("raw_payload") or {}),
                ),
            )
            self._commit(conn)
        return {"ok": True, "request_id": item.request_id}

    def get_request(self, request_id: str) -> CounterfactualRequest | None:
        return self._safe(lambda: self._get_request(request_id), None)

    def _get_request(self, request_id: str) -> CounterfactualRequest | None:
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM counterfactual_requests WHERE request_id=?", (request_id,)).fetchone()
        return _request_from_row(row)

    def list_requests(self, limit: int = 100) -> list[CounterfactualRequest]:
        return self._safe(lambda: self._list_requests(limit), [])

    def _list_requests(self, limit: int = 100) -> list[CounterfactualRequest]:
        with self.connection() as conn:
            rows = conn.execute("SELECT * FROM counterfactual_requests ORDER BY created_at DESC LIMIT ?", (max(1, int(limit)),)).fetchall()
        return [item for item in (_request_from_row(row) for row in rows) if item is not None]

    def save_evidence(self, evidence: CounterfactualEvidence) -> dict[str, Any]:
        return self._safe(lambda: self._save_evidence(evidence), {"ok": False, "evidence_id": getattr(evidence, "evidence_id", "")})

    def _save_evidence(self, evidence: CounterfactualEvidence) -> dict[str, Any]:
        item = CounterfactualEvidence.from_dict(evidence)
        data = item.to_dict()
        with self.connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO counterfactual_evidence
                (evidence_id, request_id, source_decision_id, source_alpha_id, action_id, action_type,
                 similarity_score, reward, success, platform_sc_abs_max, quality_passed, reason_codes_json, raw_payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.evidence_id,
                    item.request_id,
                    item.source_decision_id,
                    item.source_alpha_id,
                    item.action_id,
                    item.action_type,
                    item.similarity_score,
                    item.reward,
                    _bool_to_int(item.success),
                    item.platform_sc_abs_max,
                    _bool_to_int(item.quality_passed),
                    json_dumps_safe(data.get("reason_codes") or []),
                    json_dumps_safe(data.get("raw_payload") or {}),
                ),
            )
            self._commit(conn)
        return {"ok": True, "evidence_id": item.evidence_id}

    def list_evidence(self, request_id: str) -> list[CounterfactualEvidence]:
        return self._safe(lambda: self._list_evidence(request_id), [])

    def _list_evidence(self, request_id: str) -> list[CounterfactualEvidence]:
        with self.connection() as conn:
            rows = conn.execute("SELECT * FROM counterfactual_evidence WHERE request_id=? ORDER BY similarity_score DESC", (request_id,)).fetchall()
        return [item for item in (_evidence_from_row(row) for row in rows) if item is not None]

    def save_estimate(self, estimate: CounterfactualEstimate) -> dict[str, Any]:
        return self._safe(lambda: self._save_estimate(estimate), {"ok": False, "estimate_id": getattr(estimate, "estimate_id", "")})

    def _save_estimate(self, estimate: CounterfactualEstimate) -> dict[str, Any]:
        item = CounterfactualEstimate.from_dict(estimate)
        data = item.to_dict()
        with self.connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO counterfactual_estimates
                (estimate_id, request_id, decision_id, target_action_json, evidence_count, effective_evidence_count,
                 estimated_reward, estimated_success_rate, estimated_platform_sc_abs_max, estimated_quality_pass_rate,
                 confidence, verdict, risk_flags_json, reason_codes_json, estimated_not_observed, created_at, raw_payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.estimate_id,
                    item.request_id,
                    item.decision_id,
                    json_dumps_safe(data.get("target_action_json")) if data.get("target_action_json") is not None else None,
                    item.evidence_count,
                    item.effective_evidence_count,
                    item.estimated_reward,
                    item.estimated_success_rate,
                    item.estimated_platform_sc_abs_max,
                    item.estimated_quality_pass_rate,
                    item.confidence,
                    item.verdict,
                    json_dumps_safe(data.get("risk_flags") or []),
                    json_dumps_safe(data.get("reason_codes") or []),
                    _bool_to_int(item.estimated_not_observed),
                    item.created_at,
                    json_dumps_safe(data.get("raw_payload") or {}),
                ),
            )
            self._commit(conn)
        return {"ok": True, "estimate_id": item.estimate_id}

    def get_estimate(self, estimate_id: str) -> CounterfactualEstimate | None:
        return self._safe(lambda: self._get_estimate(estimate_id), None)

    def _get_estimate(self, estimate_id: str) -> CounterfactualEstimate | None:
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM counterfactual_estimates WHERE estimate_id=?", (estimate_id,)).fetchone()
        return _estimate_from_row(row)

    def list_estimates(self, decision_type: str | None = None, verdict: str | None = None, limit: int = 100) -> list[CounterfactualEstimate]:
        return self._safe(lambda: self._list_estimates(decision_type=decision_type, verdict=verdict, limit=limit), [])

    def _list_estimates(self, decision_type: str | None = None, verdict: str | None = None, limit: int = 100) -> list[CounterfactualEstimate]:
        clauses: list[str] = []
        params: list[Any] = []
        if decision_type:
            clauses.append("r.decision_type=?")
            params.append(decision_type)
        if verdict:
            clauses.append("e.verdict=?")
            params.append(verdict)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        params.append(max(1, int(limit)))
        with self.connection() as conn:
            rows = conn.execute(f"SELECT e.* FROM counterfactual_estimates e LEFT JOIN counterfactual_requests r ON r.request_id=e.request_id{where} ORDER BY e.created_at DESC LIMIT ?", tuple(params)).fetchall()
        return [item for item in (_estimate_from_row(row) for row in rows) if item is not None]

    def update_summary(self, decision_type: str | None = None) -> CounterfactualSummary | None:
        return self._safe(lambda: self._update_summary(decision_type), None)

    def _update_summary(self, decision_type: str | None = None) -> CounterfactualSummary:
        clauses: list[str] = []
        params: list[Any] = []
        if decision_type:
            clauses.append("r.decision_type=?")
            params.append(decision_type)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self.connection() as conn:
            requests = conn.execute("SELECT COUNT(*) AS n FROM counterfactual_requests" + (" WHERE decision_type=?" if decision_type else ""), tuple([decision_type] if decision_type else [])).fetchone()
            estimates = conn.execute(f"SELECT e.*, r.decision_type FROM counterfactual_estimates e LEFT JOIN counterfactual_requests r ON r.request_id=e.request_id{where}", tuple(params)).fetchall()
            estimate_count = len(estimates)
            insufficient = sum(1 for row in estimates if row["verdict"] == "insufficient_evidence")
            high_risk = sum(1 for row in estimates if row["verdict"] == "high_risk_estimate")
            med_hi = sum(1 for row in estimates if row["confidence"] in {"medium", "high"})
            evidence_counts = [int(row["evidence_count"] or 0) for row in estimates]
            summary = CounterfactualSummary(
                summary_id=f"counterfactual_summary:{decision_type or 'all'}",
                decision_type=decision_type,
                request_count=int(requests["n"] if requests is not None and hasattr(requests, "keys") else 0),
                estimate_count=estimate_count,
                insufficient_count=insufficient,
                high_risk_count=high_risk,
                medium_or_high_confidence_count=med_hi,
                avg_evidence_count=(sum(evidence_counts) / len(evidence_counts)) if evidence_counts else None,
                updated_at=utc_now_iso(),
                raw_payload={"mode": "advisory", "estimated_not_observed": True},
            )
            data = summary.to_dict()
            conn.execute(
                """
                INSERT OR REPLACE INTO counterfactual_summaries
                (summary_id, decision_type, request_count, estimate_count, insufficient_count, high_risk_count,
                 medium_or_high_confidence_count, avg_evidence_count, updated_at, raw_payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    summary.summary_id,
                    summary.decision_type,
                    summary.request_count,
                    summary.estimate_count,
                    summary.insufficient_count,
                    summary.high_risk_count,
                    summary.medium_or_high_confidence_count,
                    summary.avg_evidence_count,
                    summary.updated_at,
                    json_dumps_safe(data.get("raw_payload") or {}),
                ),
            )
            self._commit(conn)
        return summary

    def list_summaries(self) -> list[CounterfactualSummary]:
        return self._safe(lambda: self._list_summaries(), [])

    def _list_summaries(self) -> list[CounterfactualSummary]:
        with self.connection() as conn:
            rows = conn.execute("SELECT * FROM counterfactual_summaries ORDER BY decision_type").fetchall()
        return [item for item in (_summary_from_row(row) for row in rows) if item is not None]

    def _safe(self, call: Any, default: Any) -> Any:
        try:
            self.last_error = ""
            return call()
        except Exception as exc:
            self.last_error = str(exc)
            try:
                if self.logger is not None:
                    self.logger.warning("counterfactual repository failure: %s", exc)
            except Exception:
                pass
            return default

    def _commit(self, conn: sqlite3.Connection) -> None:
        try:
            conn.commit()
        except Exception:
            pass


def _request_from_row(row: Any) -> CounterfactualRequest | None:
    if row is None or not hasattr(row, "keys"):
        return None
    data = dict(row)
    return CounterfactualRequest.from_dict({
        "request_id": data.get("request_id"),
        "replay_run_id": data.get("replay_run_id"),
        "policy_decision_id": data.get("policy_decision_id"),
        "decision_id": data.get("decision_id"),
        "decision_type": data.get("decision_type"),
        "target_action": json_loads_safe(data.get("target_action_json"), None),
        "actual_action": json_loads_safe(data.get("actual_action_json"), None),
        "alpha_id": data.get("alpha_id"),
        "experiment_id": data.get("experiment_id"),
        "arm_id": data.get("arm_id"),
        "budget_plan_id": data.get("budget_plan_id"),
        "features": json_loads_safe(data.get("features_json"), {}),
        "context": json_loads_safe(data.get("context_json"), {}),
        "min_evidence": data.get("min_evidence"),
        "created_at": data.get("created_at"),
        "raw_payload": json_loads_safe(data.get("raw_payload"), {}),
    })


def _evidence_from_row(row: Any) -> CounterfactualEvidence | None:
    if row is None or not hasattr(row, "keys"):
        return None
    data = dict(row)
    return CounterfactualEvidence.from_dict({
        "evidence_id": data.get("evidence_id"),
        "request_id": data.get("request_id"),
        "source_decision_id": data.get("source_decision_id"),
        "source_alpha_id": data.get("source_alpha_id"),
        "action_id": data.get("action_id"),
        "action_type": data.get("action_type"),
        "similarity_score": data.get("similarity_score"),
        "reward": data.get("reward"),
        "success": data.get("success"),
        "platform_sc_abs_max": data.get("platform_sc_abs_max"),
        "quality_passed": data.get("quality_passed"),
        "reason_codes": json_loads_safe(data.get("reason_codes_json"), []),
        "raw_payload": json_loads_safe(data.get("raw_payload"), {}),
    })


def _estimate_from_row(row: Any) -> CounterfactualEstimate | None:
    if row is None or not hasattr(row, "keys"):
        return None
    data = dict(row)
    return CounterfactualEstimate.from_dict({
        "estimate_id": data.get("estimate_id"),
        "request_id": data.get("request_id"),
        "decision_id": data.get("decision_id"),
        "target_action_json": json_loads_safe(data.get("target_action_json"), None),
        "evidence_count": data.get("evidence_count"),
        "effective_evidence_count": data.get("effective_evidence_count"),
        "estimated_reward": data.get("estimated_reward"),
        "estimated_success_rate": data.get("estimated_success_rate"),
        "estimated_platform_sc_abs_max": data.get("estimated_platform_sc_abs_max"),
        "estimated_quality_pass_rate": data.get("estimated_quality_pass_rate"),
        "confidence": data.get("confidence"),
        "verdict": data.get("verdict"),
        "risk_flags": json_loads_safe(data.get("risk_flags_json"), []),
        "reason_codes": json_loads_safe(data.get("reason_codes_json"), []),
        "estimated_not_observed": data.get("estimated_not_observed"),
        "created_at": data.get("created_at"),
        "raw_payload": json_loads_safe(data.get("raw_payload"), {}),
    })


def _summary_from_row(row: Any) -> CounterfactualSummary | None:
    if row is None or not hasattr(row, "keys"):
        return None
    data = dict(row)
    return CounterfactualSummary.from_dict({
        "summary_id": data.get("summary_id"),
        "decision_type": data.get("decision_type"),
        "request_count": data.get("request_count"),
        "estimate_count": data.get("estimate_count"),
        "insufficient_count": data.get("insufficient_count"),
        "high_risk_count": data.get("high_risk_count"),
        "medium_or_high_confidence_count": data.get("medium_or_high_confidence_count"),
        "avg_evidence_count": data.get("avg_evidence_count"),
        "updated_at": data.get("updated_at"),
        "raw_payload": json_loads_safe(data.get("raw_payload"), {}),
    })


def _bool_to_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return 1 if bool(value) else 0
