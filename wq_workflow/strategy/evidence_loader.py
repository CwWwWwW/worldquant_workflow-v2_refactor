from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Sequence

from wq_workflow.data.json_utils import json_loads_safe, safe_float, safe_int
from .schema import StrategyEvidence, utc_now_iso


def _evidence_id(prefix: str, *parts: Any) -> str:
    raw = ":".join(str(part or "") for part in parts if part is not None)
    safe = "".join(ch if ch.isalnum() or ch in {"_", "-", ":"} else "_" for ch in raw)[:160]
    return f"{prefix}:{safe or utc_now_iso()}"


_ALLOWED_TABLES = {
    "counterfactual_estimates",
    "counterfactual_summaries",
    "decision_outcomes",
    "decision_snapshots",
    "experiment_budget_allocations",
    "experiment_budget_plans",
    "experiment_budget_snapshots",
    "ml_model_registry",
    "ml_prediction_audit",
    "ml_training_samples",
    "model_safety_reports",
    "offline_replay_comparisons",
    "offline_replay_policy_metrics",
}


class StrategyEvidenceLoader:
    def __init__(self, *, storage: Any | None = None, db_path: str | Path | None = None, config: Any | None = None, logger: Any | None = None, read_only: bool = True) -> None:
        self.storage = storage
        path = db_path if db_path is not None else getattr(getattr(storage, "config", None), "db_path", None)
        if path is None and config is not None:
            path = getattr(config, "storage_db_path", None)
        self.db_path = Path(path) if path is not None else None
        self.config = config
        self.logger = logger
        self.read_only = bool(read_only)
        self.warnings: list[str] = []

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        if self.db_path is None:
            raise RuntimeError("database path unavailable")
        if self.read_only:
            if not self.db_path.exists():
                raise FileNotFoundError(f"missing_db:{self.db_path}")
            conn = sqlite3.connect(f"file:{self.db_path.as_posix()}?mode=ro", uri=True, timeout=1.0)
        else:
            from wq_workflow.data.migrations import initialize_refactor_tables
            from wq_workflow.storage.schema import initialize_schema
            from wq_workflow.storage.sqlite_store import connect_db

            conn = connect_db(self.db_path)
            initialize_schema(conn)
            initialize_refactor_tables(conn)
        try:
            yield conn
        finally:
            conn.close()

    def load_all_evidence(self) -> list[StrategyEvidence]:
        evidence: list[StrategyEvidence] = []
        for loader in (
            self.load_experiment_evidence,
            self.load_replay_evidence,
            self.load_counterfactual_evidence,
            self.load_governance_evidence,
            self.load_ml_registry_evidence,
            self.load_legacy_baseline_evidence,
        ):
            try:
                evidence.extend(loader())
            except Exception as exc:
                self._warn(f"{loader.__name__}_failed: {exc}")
        return evidence

    def load_experiment_evidence(self) -> list[StrategyEvidence]:
        rows: list[StrategyEvidence] = []
        count = self._count("experiment_budget_allocations") + self._count("experiment_budget_plans") + self._count("experiment_budget_snapshots")
        if count:
            rows.append(StrategyEvidence(evidence_id=_evidence_id("experiment_summary", count), strategy_id="experiment_budget", evidence_type="experiment_summary", sample_count=count, reason_codes=["experiment_budget_advisory_evidence"], raw_payload={"budget_artifact_count": count}))
        report = self._read_status_json(getattr(self.config, "experiment_status_path", "runtime/status/experiment_report.json"))
        if report:
            rows.append(StrategyEvidence(evidence_id=_evidence_id("experiment_report", report.get("updated_at") or count), strategy_id="experiment_budget", evidence_type="experiment_summary", sample_count=safe_int(report.get("assignment_count") or report.get("result_count"), 0) or 0, risk_flags=list(report.get("risk_flags") or []), reason_codes=["experiment_report_json"], raw_payload={"report": report}))
        return rows

    def load_replay_evidence(self) -> list[StrategyEvidence]:
        evidence: list[StrategyEvidence] = []
        for row in self._query("SELECT * FROM offline_replay_policy_metrics ORDER BY rowid DESC LIMIT ?", "offline_replay_policy_metrics", (self._limit(),)):
            reasons = json_loads_safe(row.get("reason_codes_json"), [])
            evidence.append(StrategyEvidence(
                evidence_id=_evidence_id("replay_metrics", row.get("metric_id"), row.get("policy_name"), row.get("decision_type")),
                strategy_id="replay_supported_policy",
                evidence_type="replay_metrics",
                sample_count=safe_int(row.get("sample_count"), 0) or 0,
                avg_reward=safe_float(row.get("avg_reward"), None),
                success_rate=safe_float(row.get("success_rate"), None),
                avg_platform_sc_abs_max=safe_float(row.get("avg_platform_sc_abs_max"), None),
                quality_pass_rate=safe_float(row.get("quality_pass_rate"), None),
                replay_confidence=self._confidence_from_sample(safe_int(row.get("observable_count") or row.get("sample_count"), 0) or 0),
                reason_codes=[str(x) for x in reasons] if isinstance(reasons, list) else [],
                raw_payload=dict(row),
            ))
        for row in self._query("SELECT * FROM offline_replay_comparisons ORDER BY created_at DESC LIMIT ?", "offline_replay_comparisons", (self._limit(),)):
            risk_flags = []
            if (safe_float(row.get("sc_risk_delta"), 0.0) or 0.0) > 0:
                risk_flags.append("replay_sc_risk_delta_positive")
            evidence.append(StrategyEvidence(
                evidence_id=_evidence_id("replay_comparison", row.get("comparison_id"), row.get("challenger_policy")),
                strategy_id="replay_supported_policy",
                evidence_type="replay_comparison",
                sample_count=0,
                avg_reward=safe_float(row.get("reward_delta"), None),
                success_rate=safe_float(row.get("success_rate_delta"), None),
                avg_platform_sc_abs_max=safe_float(row.get("sc_risk_delta"), None),
                replay_confidence=str(row.get("confidence") or "low"),
                risk_flags=risk_flags,
                reason_codes=[str(row.get("verdict") or "replay_comparison")],
                raw_payload=dict(row),
            ))
        if not self._read_status_json(getattr(self.config, "offline_replay_status_path", "runtime/status/offline_replay_report.json")):
            self._warn("offline_replay_report_missing")
        return evidence

    def load_counterfactual_evidence(self) -> list[StrategyEvidence]:
        evidence: list[StrategyEvidence] = []
        for row in self._query("SELECT * FROM counterfactual_estimates ORDER BY created_at DESC LIMIT ?", "counterfactual_estimates", (self._limit(),)):
            risk_flags = json_loads_safe(row.get("risk_flags_json"), [])
            reason_codes = json_loads_safe(row.get("reason_codes_json"), [])
            flags = [str(item) for item in risk_flags] if isinstance(risk_flags, list) else []
            flags.append("estimated_not_observed")
            if str(row.get("verdict") or "").lower() in {"high_risk", "blocked", "reject"}:
                flags.append("high_risk_estimate")
            evidence.append(StrategyEvidence(
                evidence_id=_evidence_id("counterfactual_estimate", row.get("estimate_id")),
                strategy_id="counterfactual_supported_policy",
                evidence_type="counterfactual_estimate",
                sample_count=safe_int(row.get("effective_evidence_count") or row.get("evidence_count"), 0) or 0,
                avg_reward=safe_float(row.get("estimated_reward"), None),
                success_rate=safe_float(row.get("estimated_success_rate"), None),
                avg_platform_sc_abs_max=safe_float(row.get("estimated_platform_sc_abs_max"), None),
                quality_pass_rate=safe_float(row.get("estimated_quality_pass_rate"), None),
                counterfactual_confidence=str(row.get("confidence") or "insufficient"),
                risk_flags=list(dict.fromkeys(flags)),
                reason_codes=list(dict.fromkeys(["counterfactual_estimated_not_actual", *([str(item) for item in reason_codes] if isinstance(reason_codes, list) else [])])),
                raw_payload={**dict(row), "estimated_not_observed": True, "actual_outcome": False},
            ))
        for row in self._query("SELECT * FROM counterfactual_summaries ORDER BY updated_at DESC LIMIT ?", "counterfactual_summaries", (self._limit(),)):
            flags = ["counterfactual_summary_estimated_not_actual"]
            if (safe_int(row.get("high_risk_count"), 0) or 0) > 0:
                flags.append("high_risk_estimate")
            evidence.append(StrategyEvidence(evidence_id=_evidence_id("counterfactual_summary", row.get("summary_id"), row.get("decision_type")), strategy_id="counterfactual_supported_policy", evidence_type="counterfactual_summary", sample_count=safe_int(row.get("estimate_count"), 0) or 0, counterfactual_confidence=self._confidence_from_sample(safe_int(row.get("medium_or_high_confidence_count"), 0) or 0), risk_flags=flags, reason_codes=["counterfactual_summary_estimated_not_actual"], raw_payload={**dict(row), "estimated_not_observed": True, "actual_outcome": False}))
        if not self._read_status_json(getattr(self.config, "counterfactual_status_path", "runtime/status/counterfactual_report.json")):
            self._warn("counterfactual_report_missing")
        return evidence

    def load_governance_evidence(self) -> list[StrategyEvidence]:
        evidence: list[StrategyEvidence] = []
        for row in self._query("SELECT * FROM model_safety_reports ORDER BY created_at DESC LIMIT ?", "model_safety_reports", (self._limit(),)):
            status = str(row.get("safety_status") or "unknown")
            risk_flags = [] if status in {"pass", "passed", "safe"} else ["governance_blocked"]
            evidence.append(StrategyEvidence(evidence_id=_evidence_id("governance_status", row.get("report_id"), row.get("strategy_id")), strategy_id="governance_safe_policy", evidence_type="governance_status", sample_count=1, governance_status=status, risk_flags=risk_flags, reason_codes=[str(row.get("reason") or status)], raw_payload=dict(row)))
        status_payload = self._read_status_json(getattr(self.config, "governance_status_path", "runtime/status/governance_status.json"))
        if status_payload:
            status = str(status_payload.get("status") or status_payload.get("governance_status") or "unknown")
            flags = [] if status.lower() in {"ok", "ready", "pass", "safe"} else ["governance_status_not_ready"]
            evidence.append(StrategyEvidence(evidence_id=_evidence_id("governance_status_json", status_payload.get("updated_at") or status), strategy_id="governance_safe_policy", evidence_type="governance_status", sample_count=1, governance_status=status, risk_flags=flags, reason_codes=["governance_status_json"], raw_payload=status_payload))
        return evidence

    def load_ml_registry_evidence(self) -> list[StrategyEvidence]:
        evidence: list[StrategyEvidence] = []
        for task, strategy_id in {"parent": "ml_parent_policy", "policy": "ml_mutation_policy"}.items():
            sample_count = self._count("ml_training_samples", where="task_name=?", params=(task,))
            active_models = self._count("ml_model_registry", where="task_name=? AND is_active=1", params=(task,))
            audits = self._count("ml_prediction_audit", where="task_name=?", params=(task,))
            total = sample_count + audits
            if total or active_models:
                evidence.append(StrategyEvidence(evidence_id=_evidence_id("ml_registry", task, total, active_models), strategy_id=strategy_id, evidence_type="ml_registry", sample_count=total, reason_codes=["ml_registry_summary"], raw_payload={"task_name": task, "training_sample_count": sample_count, "prediction_audit_count": audits, "active_model_count": active_models}))
        return evidence

    def load_legacy_baseline_evidence(self) -> list[StrategyEvidence]:
        row = self._one("SELECT COUNT(*) AS sample_count, SUM(CASE WHEN success=1 THEN 1 ELSE 0 END) AS success_count, AVG(reward) AS avg_reward, AVG(platform_sc_abs_max) AS avg_sc, AVG(CASE WHEN quality_passed=1 THEN 1.0 ELSE 0.0 END) AS quality_rate FROM decision_outcomes", "decision_outcomes")
        if row and (safe_int(row.get("sample_count"), 0) or 0) > 0:
            sample_count = safe_int(row.get("sample_count"), 0) or 0
            success_count = safe_int(row.get("success_count"), 0) or 0
            return [StrategyEvidence(evidence_id=_evidence_id("legacy_baseline", sample_count), strategy_id="legacy_baseline", evidence_type="legacy_baseline", sample_count=sample_count, success_count=success_count, avg_reward=safe_float(row.get("avg_reward"), None), success_rate=(success_count / sample_count) if sample_count else None, avg_platform_sc_abs_max=safe_float(row.get("avg_sc"), None), quality_pass_rate=safe_float(row.get("quality_rate"), None), reason_codes=["observed_decision_outcomes"], raw_payload=dict(row))]
        snapshot_count = self._count("decision_snapshots")
        if snapshot_count:
            return [StrategyEvidence(evidence_id=_evidence_id("legacy_snapshots", snapshot_count), strategy_id="legacy_baseline", evidence_type="legacy_baseline", sample_count=snapshot_count, reason_codes=["decision_snapshots_without_outcome_summary"], raw_payload={"decision_snapshot_count": snapshot_count})]
        return []

    def _limit(self) -> int:
        return max(1, int(getattr(self.config, "strategy_scoreboard_default_limit", 1000) or 1000))

    def _confidence_from_sample(self, sample_count: int) -> str:
        if sample_count < int(getattr(self.config, "strategy_score_min_samples", 30) or 30):
            return "insufficient"
        if sample_count < int(getattr(self.config, "strategy_score_medium_samples", 100) or 100):
            return "low"
        if sample_count < int(getattr(self.config, "strategy_score_high_samples", 500) or 500):
            return "medium"
        return "high"

    def _read_status_json(self, path_value: str | Path | None) -> dict[str, Any]:
        if not path_value:
            return {}
        path = Path(path_value)
        if not path.is_absolute():
            path = Path.cwd() / path
        try:
            payload = json_loads_safe(path.read_text(encoding="utf-8"), {}) if path.exists() else {}
            return payload if isinstance(payload, dict) else {}
        except Exception:
            return {}

    def _table_exists(self, conn: sqlite3.Connection, table: str) -> bool:
        if not self._is_allowed_table(table):
            return False
        row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
        return row is not None

    def _is_allowed_table(self, table: str) -> bool:
        return str(table or "") in _ALLOWED_TABLES

    def _query(self, sql: str, source_name: str, params: Sequence[Any] | None = None) -> list[dict[str, Any]]:
        if not self._is_allowed_table(source_name):
            self._warn(f"invalid_table:{source_name}")
            return []
        bound_params = tuple(params or ())
        try:
            with self.connection() as conn:
                conn.row_factory = sqlite3.Row
                if not self._table_exists(conn, source_name):
                    self._warn(f"missing_table:{source_name}")
                    return []
                rows = conn.execute(sql, bound_params).fetchall()
                return [dict(row) for row in rows if hasattr(row, "keys")]
        except FileNotFoundError:
            self._warn(f"missing_db:{self.db_path}")
            return []
        except Exception as exc:
            self._warn(f"query_failed:{source_name}:{exc}")
            return []

    def _one(self, sql: str, source_name: str, params: Sequence[Any] | None = None) -> dict[str, Any] | None:
        rows = self._query(sql, source_name, params)
        return rows[0] if rows else None

    def _count(self, table: str, where: str = "", params: Sequence[Any] | None = None) -> int:
        if not self._is_allowed_table(table):
            self._warn(f"invalid_table:{table}")
            return 0
        sql = f"SELECT COUNT(*) AS n FROM {table}"
        if where:
            sql += f" WHERE {where}"
        row = self._one(sql, table, params)
        return safe_int((row or {}).get("n"), 0) or 0

    def _warn(self, message: str) -> None:
        self.warnings.append(message)
        self.warnings = self.warnings[-100:]
        try:
            if self.logger is not None:
                self.logger.warning("strategy evidence loader: %s", message)
        except Exception:
            pass
