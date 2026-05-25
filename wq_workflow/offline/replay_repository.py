from __future__ import annotations

import hashlib
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from wq_workflow.data.json_utils import json_dumps_safe, json_loads_safe
from wq_workflow.data.migrations import initialize_refactor_tables
from wq_workflow.storage.sqlite_store import connect_db

from .schema import DecisionAction, ReplayComparison, ReplayDatasetFilter, ReplayPolicyDecision, ReplayPolicyMetrics, ReplayRun


class ReplayRepository:
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
            raise RuntimeError("offline replay database path unavailable")
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

    def save_replay_run(self, run: ReplayRun) -> dict[str, Any]:
        return self._safe(lambda: self._save_replay_run(run), {"ok": False, "replay_run_id": getattr(run, "replay_run_id", "")})

    def _save_replay_run(self, run: ReplayRun) -> dict[str, Any]:
        item = ReplayRun.from_dict(run)
        data = item.to_dict()
        with self.connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO offline_replay_runs
                (replay_run_id, name, status, policies_json, dataset_filter_json, sample_count, observable_count,
                 started_at, completed_at, raw_payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.replay_run_id,
                    item.name,
                    item.status,
                    json_dumps_safe(data.get("policies") or []),
                    json_dumps_safe(data.get("dataset_filter") or {}),
                    item.sample_count,
                    item.observable_count,
                    item.started_at,
                    item.completed_at,
                    json_dumps_safe(data.get("raw_payload") or {}),
                ),
            )
            self._commit(conn)
        return {"ok": True, "replay_run_id": item.replay_run_id}

    def get_replay_run(self, replay_run_id: str) -> ReplayRun | None:
        return self._safe(lambda: self._get_replay_run(replay_run_id), None)

    def _get_replay_run(self, replay_run_id: str) -> ReplayRun | None:
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM offline_replay_runs WHERE replay_run_id=?", (replay_run_id,)).fetchone()
        return _run_from_row(row)

    def list_replay_runs(self, limit: int = 20) -> list[ReplayRun]:
        return self._safe(lambda: self._list_replay_runs(limit), [])

    def _list_replay_runs(self, limit: int = 20) -> list[ReplayRun]:
        with self.connection() as conn:
            rows = conn.execute("SELECT * FROM offline_replay_runs ORDER BY started_at DESC LIMIT ?", (max(1, int(limit)),)).fetchall()
        return [item for item in (_run_from_row(row) for row in rows) if item is not None]

    def save_policy_decision(self, decision: ReplayPolicyDecision) -> dict[str, Any]:
        return self._safe(lambda: self._save_policy_decision(decision), {"ok": False, "policy_decision_id": getattr(decision, "policy_decision_id", "")})

    def _save_policy_decision(self, decision: ReplayPolicyDecision) -> dict[str, Any]:
        item = ReplayPolicyDecision.from_dict(decision)
        data = item.to_dict()
        with self.connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO offline_replay_policy_decisions
                (policy_decision_id, replay_run_id, decision_id, policy_name, selected_action_json,
                 selected_matches_actual, selected_matches_legacy, observable_outcome, reward, success,
                 platform_sc_abs_max, quality_passed, reason_codes_json, created_at, raw_payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.policy_decision_id,
                    item.replay_run_id,
                    item.decision_id,
                    item.policy_name,
                    json_dumps_safe(data.get("selected_action")) if data.get("selected_action") is not None else None,
                    _bool_to_int(item.selected_matches_actual),
                    _bool_to_int(item.selected_matches_legacy),
                    _bool_to_int(item.observable_outcome),
                    item.reward,
                    _bool_to_int(item.success),
                    item.platform_sc_abs_max,
                    _bool_to_int(item.quality_passed),
                    json_dumps_safe(data.get("reason_codes") or []),
                    item.created_at,
                    json_dumps_safe(data.get("raw_payload") or {}),
                ),
            )
            self._commit(conn)
        return {"ok": True, "policy_decision_id": item.policy_decision_id}

    def list_policy_decisions(self, replay_run_id: str, policy_name: str | None = None) -> list[ReplayPolicyDecision]:
        return self._safe(lambda: self._list_policy_decisions(replay_run_id, policy_name), [])

    def _list_policy_decisions(self, replay_run_id: str, policy_name: str | None = None) -> list[ReplayPolicyDecision]:
        params: list[Any] = [replay_run_id]
        where = "replay_run_id=?"
        if policy_name:
            where += " AND policy_name=?"
            params.append(policy_name)
        with self.connection() as conn:
            rows = conn.execute(f"SELECT * FROM offline_replay_policy_decisions WHERE {where} ORDER BY created_at", tuple(params)).fetchall()
        return [item for item in (_decision_from_row(row) for row in rows) if item is not None]

    def save_policy_metrics(self, metrics: ReplayPolicyMetrics) -> dict[str, Any]:
        return self._safe(lambda: self._save_policy_metrics(metrics), {"ok": False})

    def _save_policy_metrics(self, metrics: ReplayPolicyMetrics) -> dict[str, Any]:
        item = ReplayPolicyMetrics.from_dict(metrics)
        metric_id = _metric_id(item)
        data = item.to_dict()
        with self.connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO offline_replay_policy_metrics
                (metric_id, replay_run_id, policy_name, decision_type, sample_count, observable_count, coverage_rate,
                 agreement_with_actual_rate, agreement_with_legacy_rate, avg_reward, success_rate,
                 avg_platform_sc_abs_max, quality_pass_rate, insufficient_evidence_count, reason_codes_json, raw_payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    metric_id,
                    item.replay_run_id,
                    item.policy_name,
                    item.decision_type,
                    item.sample_count,
                    item.observable_count,
                    item.coverage_rate,
                    item.agreement_with_actual_rate,
                    item.agreement_with_legacy_rate,
                    item.avg_reward,
                    item.success_rate,
                    item.avg_platform_sc_abs_max,
                    item.quality_pass_rate,
                    item.insufficient_evidence_count,
                    json_dumps_safe(data.get("reason_codes") or []),
                    json_dumps_safe(data.get("raw_payload") or {}),
                ),
            )
            self._commit(conn)
        return {"ok": True, "metric_id": metric_id}

    def list_policy_metrics(self, replay_run_id: str) -> list[ReplayPolicyMetrics]:
        return self._safe(lambda: self._list_policy_metrics(replay_run_id), [])

    def _list_policy_metrics(self, replay_run_id: str) -> list[ReplayPolicyMetrics]:
        with self.connection() as conn:
            rows = conn.execute("SELECT * FROM offline_replay_policy_metrics WHERE replay_run_id=? ORDER BY policy_name, decision_type", (replay_run_id,)).fetchall()
        return [item for item in (_metrics_from_row(row) for row in rows) if item is not None]

    def save_comparison(self, comparison: ReplayComparison) -> dict[str, Any]:
        return self._safe(lambda: self._save_comparison(comparison), {"ok": False, "comparison_id": getattr(comparison, "comparison_id", "")})

    def _save_comparison(self, comparison: ReplayComparison) -> dict[str, Any]:
        item = ReplayComparison.from_dict(comparison)
        data = item.to_dict()
        with self.connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO offline_replay_comparisons
                (comparison_id, replay_run_id, baseline_policy, challenger_policy, decision_type, baseline_metrics_json,
                 challenger_metrics_json, reward_delta, success_rate_delta, sc_risk_delta, quality_pass_delta,
                 confidence, verdict, created_at, raw_payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.comparison_id,
                    item.replay_run_id,
                    item.baseline_policy,
                    item.challenger_policy,
                    item.decision_type,
                    json_dumps_safe(data.get("baseline_metrics") or {}),
                    json_dumps_safe(data.get("challenger_metrics") or {}),
                    item.reward_delta,
                    item.success_rate_delta,
                    item.sc_risk_delta,
                    item.quality_pass_delta,
                    item.confidence,
                    item.verdict,
                    item.created_at,
                    json_dumps_safe(data.get("raw_payload") or {}),
                ),
            )
            self._commit(conn)
        return {"ok": True, "comparison_id": item.comparison_id}

    def list_comparisons(self, replay_run_id: str) -> list[ReplayComparison]:
        return self._safe(lambda: self._list_comparisons(replay_run_id), [])

    def _list_comparisons(self, replay_run_id: str) -> list[ReplayComparison]:
        with self.connection() as conn:
            rows = conn.execute("SELECT * FROM offline_replay_comparisons WHERE replay_run_id=? ORDER BY created_at", (replay_run_id,)).fetchall()
        return [item for item in (_comparison_from_row(row) for row in rows) if item is not None]

    def _safe(self, call: Any, default: Any) -> Any:
        try:
            self.last_error = ""
            return call()
        except Exception as exc:
            self.last_error = str(exc)
            try:
                if self.logger is not None:
                    self.logger.warning("offline replay repository failure: %s", exc)
            except Exception:
                pass
            return default

    def _commit(self, conn: sqlite3.Connection) -> None:
        try:
            conn.commit()
        except Exception:
            pass


def _run_from_row(row: Any) -> ReplayRun | None:
    if row is None or not hasattr(row, "keys"):
        return None
    data = dict(row)
    return ReplayRun.from_dict(
        {
            "replay_run_id": data.get("replay_run_id"),
            "name": data.get("name"),
            "status": data.get("status"),
            "policies": json_loads_safe(data.get("policies_json"), []),
            "dataset_filter": json_loads_safe(data.get("dataset_filter_json"), {}),
            "sample_count": data.get("sample_count"),
            "observable_count": data.get("observable_count"),
            "started_at": data.get("started_at"),
            "completed_at": data.get("completed_at"),
            "raw_payload": json_loads_safe(data.get("raw_payload"), {}),
        }
    )


def _decision_from_row(row: Any) -> ReplayPolicyDecision | None:
    if row is None or not hasattr(row, "keys"):
        return None
    data = dict(row)
    selected = json_loads_safe(data.get("selected_action_json"), None)
    return ReplayPolicyDecision.from_dict(
        {
            "policy_decision_id": data.get("policy_decision_id"),
            "replay_run_id": data.get("replay_run_id"),
            "decision_id": data.get("decision_id"),
            "policy_name": data.get("policy_name"),
            "selected_action": DecisionAction.from_dict(selected).to_dict() if selected else None,
            "selected_matches_actual": data.get("selected_matches_actual"),
            "selected_matches_legacy": data.get("selected_matches_legacy"),
            "observable_outcome": data.get("observable_outcome"),
            "reward": data.get("reward"),
            "success": data.get("success"),
            "platform_sc_abs_max": data.get("platform_sc_abs_max"),
            "quality_passed": data.get("quality_passed"),
            "reason_codes": json_loads_safe(data.get("reason_codes_json"), []),
            "created_at": data.get("created_at"),
            "raw_payload": json_loads_safe(data.get("raw_payload"), {}),
        }
    )


def _metrics_from_row(row: Any) -> ReplayPolicyMetrics | None:
    if row is None or not hasattr(row, "keys"):
        return None
    data = dict(row)
    return ReplayPolicyMetrics.from_dict(
        {
            "replay_run_id": data.get("replay_run_id"),
            "policy_name": data.get("policy_name"),
            "decision_type": data.get("decision_type"),
            "sample_count": data.get("sample_count"),
            "observable_count": data.get("observable_count"),
            "coverage_rate": data.get("coverage_rate"),
            "agreement_with_actual_rate": data.get("agreement_with_actual_rate"),
            "agreement_with_legacy_rate": data.get("agreement_with_legacy_rate"),
            "avg_reward": data.get("avg_reward"),
            "success_rate": data.get("success_rate"),
            "avg_platform_sc_abs_max": data.get("avg_platform_sc_abs_max"),
            "quality_pass_rate": data.get("quality_pass_rate"),
            "insufficient_evidence_count": data.get("insufficient_evidence_count"),
            "reason_codes": json_loads_safe(data.get("reason_codes_json"), []),
            "raw_payload": json_loads_safe(data.get("raw_payload"), {}),
        }
    )


def _comparison_from_row(row: Any) -> ReplayComparison | None:
    if row is None or not hasattr(row, "keys"):
        return None
    data = dict(row)
    return ReplayComparison.from_dict(
        {
            "comparison_id": data.get("comparison_id"),
            "replay_run_id": data.get("replay_run_id"),
            "baseline_policy": data.get("baseline_policy"),
            "challenger_policy": data.get("challenger_policy"),
            "decision_type": data.get("decision_type"),
            "baseline_metrics": json_loads_safe(data.get("baseline_metrics_json"), {}),
            "challenger_metrics": json_loads_safe(data.get("challenger_metrics_json"), {}),
            "reward_delta": data.get("reward_delta"),
            "success_rate_delta": data.get("success_rate_delta"),
            "sc_risk_delta": data.get("sc_risk_delta"),
            "quality_pass_delta": data.get("quality_pass_delta"),
            "confidence": data.get("confidence"),
            "verdict": data.get("verdict"),
            "created_at": data.get("created_at"),
            "raw_payload": json_loads_safe(data.get("raw_payload"), {}),
        }
    )


def _metric_id(metrics: ReplayPolicyMetrics) -> str:
    seed = f"{metrics.replay_run_id}|{metrics.policy_name}|{metrics.decision_type or ''}"
    return "replay_metric:" + hashlib.sha256(seed.encode("utf-8", errors="replace")).hexdigest()[:24]


def _bool_to_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return 1 if bool(value) else 0
