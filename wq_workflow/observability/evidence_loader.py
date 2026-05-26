from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from wq_workflow import paths
from wq_workflow.data.json_utils import json_loads_safe

from .explanation_schema import ExplanationEvidence
from .utils import clean_dict, clean_list, utc_now_iso


class ExplanationEvidenceLoader:
    def __init__(self, *, config: Any | None = None, db_path: str | Path | None = None, root: str | Path | None = None, logger: Any | None = None) -> None:
        self.config = config
        self.root = Path(root or paths.ROOT)
        self.db_path = Path(db_path or getattr(config, "storage_db_path", "runtime/db/workflow.db"))
        if not self.db_path.is_absolute():
            self.db_path = self.root / self.db_path
        self.logger = logger
        self.warnings: list[str] = []
        self._warning_keys: set[str] = set()
        self.limit = int(getattr(config, "observability_explanation_recent_limit", 1000) or 1000)

    def load_all_evidence(self) -> list[ExplanationEvidence]:
        self.warnings = []
        self._warning_keys = set()
        loaders = [
            self.load_observability_metrics_evidence,
            self.load_alerts_evidence,
            self.load_diagnosis_evidence,
            self.load_strategy_evidence,
            self.load_budget_evidence,
            self.load_offline_evidence,
            self.load_counterfactual_evidence,
            self.load_experiment_evidence,
            self.load_governance_evidence,
            self.load_system_evidence,
        ]
        evidence: list[ExplanationEvidence] = []
        for loader in loaders:
            try:
                evidence.extend(loader())
            except Exception as exc:
                self._warn(f"evidence_loader_failed:{loader.__name__}:{exc}")
        if self.warnings:
            evidence.append(self._system_evidence("evidence_loader_warnings", "; ".join(self.warnings), risk_flags=["missing_or_unreadable_source"], reason_codes=["source_unavailable", "missing_or_unreadable_source"]))
        return [ExplanationEvidence.from_dict(item) for item in evidence]

    def load_observability_metrics_evidence(self) -> list[ExplanationEvidence]:
        result: list[ExplanationEvidence] = []
        payload = self._read_status(getattr(self.config, "observability_metrics_status_path", "runtime/status/observability_metrics.json"), "observability_metrics_status")
        if payload:
            for item in clean_list(payload.get("metrics") or []):
                result.append(self._evidence_from_payload("observability_metrics", "metric", item.get("metric_name") or item.get("name") or "observability metric", item, confidence="high"))
            if payload.get("summary"):
                result.append(self._evidence_from_payload("observability_metrics", "metric", "observability metrics summary", payload.get("summary"), confidence="medium"))
        result.extend(self._load_table_rows("observability_metrics", "observability_metrics", "metric", title_field="metric_name", time_field="timestamp"))
        result.extend(self._load_table_rows("observability_summaries", "observability_metrics", "metric", title_field="summary_id", time_field="generated_at"))
        return result

    def load_alerts_evidence(self) -> list[ExplanationEvidence]:
        result: list[ExplanationEvidence] = []
        if not bool(getattr(self.config, "observability_explanation_include_alerts", True)):
            return result
        payload = self._read_status(getattr(self.config, "observability_alerts_status_path", "runtime/status/observability_alerts.json"), "observability_alerts_status")
        if payload:
            for item in clean_list(payload.get("alerts") or []):
                result.append(self._evidence_from_payload("observability_alerts", "alert", item.get("alert_name") or "alert", item, advisory=True, confidence="medium"))
            for item in clean_list(payload.get("drift_signals") or []):
                result.append(self._evidence_from_payload("observability_alerts", "alert", item.get("metric_name") or "drift signal", item, advisory=True, confidence="medium"))
        result.extend(self._load_table_rows("observability_alert_events", "observability_alerts", "alert", title_field="alert_name", time_field="created_at", advisory=True))
        return result

    def load_diagnosis_evidence(self) -> list[ExplanationEvidence]:
        result: list[ExplanationEvidence] = []
        if not bool(getattr(self.config, "observability_explanation_include_diagnosis", True)):
            return result
        payload = self._read_status(getattr(self.config, "observability_diagnosis_status_path", "runtime/status/health_diagnosis.json"), "health_diagnosis_status")
        if payload:
            for item in clean_list(payload.get("diagnoses") or []):
                result.append(self._evidence_from_payload("health_diagnosis", "diagnosis", item.get("area") or "health diagnosis", item, advisory=True, confidence="medium"))
        result.extend(self._load_table_rows("observability_health_diagnoses", "health_diagnosis", "diagnosis", title_field="area", time_field="created_at", advisory=True))
        result.extend(self._load_table_rows("observability_health_reports", "health_diagnosis", "diagnosis", title_field="overall_status", time_field="generated_at", advisory=True))
        return result

    def load_strategy_evidence(self) -> list[ExplanationEvidence]:
        result: list[ExplanationEvidence] = []
        for status_path, source, etype in (
            (getattr(self.config, "strategy_scoreboard_status_path", "runtime/status/strategy_scoreboard.json"), "strategy_scoreboard", "strategy_score"),
            (getattr(self.config, "strategy_portfolio_status_path", "runtime/status/strategy_portfolio_report.json"), "strategy_portfolio", "strategy_state"),
        ):
            payload = self._read_status(status_path, source)
            if payload:
                result.append(self._evidence_from_payload(source, etype, source, payload, advisory=True, confidence="medium"))
                for key in ("scores", "strategy_states", "states", "profiles"):
                    items = clean_list(payload.get(key) or [])
                    for item in items[: self.limit]:
                        result.append(self._evidence_from_payload(source, etype, item.get("strategy_id") or key, item, advisory=True, confidence=item.get("confidence") or "medium"))
        result.extend(self._load_table_rows("strategy_scores", "strategy_scoreboard", "strategy_score", title_field="strategy_id", time_field="updated_at", advisory=True))
        result.extend(self._load_table_rows("strategy_scoreboards", "strategy_scoreboard", "strategy_score", title_field="scoreboard_id", time_field="generated_at", advisory=True))
        result.extend(self._load_table_rows("strategy_portfolio_states", "strategy_portfolio", "strategy_state", title_field="strategy_id", time_field="updated_at", advisory=True))
        result.extend(self._load_table_rows("strategy_portfolio_reports", "strategy_portfolio", "strategy_state", title_field="report_id", time_field="generated_at", advisory=True))
        return result

    def load_budget_evidence(self) -> list[ExplanationEvidence]:
        result: list[ExplanationEvidence] = []
        if not bool(getattr(self.config, "observability_explanation_include_budget", True)):
            return result
        payload = self._read_status(getattr(self.config, "strategy_budget_status_path", "runtime/status/strategy_budget_report.json"), "strategy_budget_status")
        if payload:
            result.append(self._evidence_from_payload("strategy_budget", "budget_allocation", "strategy budget report", payload, advisory=True, confidence="medium"))
            for item in clean_list(payload.get("allocations") or [])[: self.limit]:
                result.append(self._evidence_from_payload("strategy_budget", "budget_allocation", item.get("strategy_id") or "budget allocation", item, advisory=True, confidence=item.get("confidence") or "medium"))
        result.extend(self._load_table_rows("strategy_budget_allocations", "strategy_budget", "budget_allocation", title_field="strategy_id", time_field="created_at", advisory=True))
        result.extend(self._load_table_rows("strategy_budget_reports", "strategy_budget", "budget_allocation", title_field="report_id", time_field="generated_at", advisory=True))
        return result

    def load_offline_evidence(self) -> list[ExplanationEvidence]:
        result: list[ExplanationEvidence] = []
        for status_path, source, etype in (
            (getattr(self.config, "decision_snapshot_status_path", "runtime/status/decision_snapshot_status.json"), "decision_snapshot", "decision_snapshot"),
            (getattr(self.config, "offline_replay_status_path", "runtime/status/offline_replay_report.json"), "offline_replay", "replay_metric"),
        ):
            payload = self._read_status(status_path, source)
            if payload:
                result.append(self._evidence_from_payload(source, etype, source, payload, advisory=source == "offline_replay", observed=False, confidence="medium"))
        result.extend(self._load_table_rows("decision_snapshots", "decision_snapshot", "decision_snapshot", title_field="decision_id", time_field="created_at"))
        result.extend(self._load_table_rows("decision_outcomes", "decision_snapshot", "actual_outcome", title_field="outcome_id", time_field="created_at", observed=True))
        result.extend(self._load_table_rows("offline_replay_runs", "offline_replay", "replay_metric", title_field="replay_run_id", time_field="started_at", advisory=True))
        result.extend(self._load_table_rows("offline_replay_policy_metrics", "offline_replay", "replay_metric", title_field="metric_id", time_field="created_at", advisory=True))
        result.extend(self._load_table_rows("offline_replay_comparisons", "offline_replay", "replay_metric", title_field="comparison_id", time_field="created_at", advisory=True))
        return result

    def load_counterfactual_evidence(self) -> list[ExplanationEvidence]:
        result: list[ExplanationEvidence] = []
        if not bool(getattr(self.config, "observability_explanation_include_counterfactual", True)):
            return result
        payload = self._read_status(getattr(self.config, "counterfactual_status_path", "runtime/status/counterfactual_report.json"), "counterfactual_status")
        if payload:
            result.append(self._evidence_from_payload("counterfactual", "counterfactual_estimate", "counterfactual report", payload, estimated=True, observed=False, advisory=True, confidence="medium"))
            for item in clean_list(payload.get("recent_estimates") or [])[: self.limit]:
                result.append(self._evidence_from_payload("counterfactual", "counterfactual_estimate", item.get("estimate_id") or "counterfactual estimate", item, estimated=True, observed=False, advisory=True, confidence=item.get("confidence") or "unknown"))
        result.extend(self._load_table_rows("counterfactual_estimates", "counterfactual", "counterfactual_estimate", title_field="estimate_id", time_field="created_at", estimated=True, advisory=True))
        result.extend(self._load_table_rows("counterfactual_summaries", "counterfactual", "counterfactual_estimate", title_field="summary_id", time_field="updated_at", estimated=True, advisory=True))
        return result

    def load_experiment_evidence(self) -> list[ExplanationEvidence]:
        result: list[ExplanationEvidence] = []
        payload = self._read_status(getattr(self.config, "experiment_status_path", "runtime/status/experiment_report.json"), "experiment_status")
        if payload:
            result.append(self._evidence_from_payload("experiment", "experiment_summary", "experiment report", payload, confidence="medium"))
            for item in clean_list(payload.get("summaries") or [])[: self.limit]:
                result.append(self._evidence_from_payload("experiment", "experiment_summary", item.get("experiment_id") or "experiment summary", item, confidence="medium"))
        result.extend(self._load_table_rows("experiment_summaries", "experiment", "experiment_summary", title_field="summary_id", time_field="updated_at"))
        result.extend(self._load_table_rows("experiment_budget_allocations", "experiment", "experiment_summary", title_field="allocation_id", time_field="created_at", advisory=True))
        return result

    def load_governance_evidence(self) -> list[ExplanationEvidence]:
        result: list[ExplanationEvidence] = []
        payload = self._read_status(getattr(self.config, "governance_status_path", "runtime/status/governance_status.json"), "governance_status")
        if payload:
            result.append(self._evidence_from_payload("governance", "governance_status", "governance status", payload, advisory=True, confidence="medium"))
        for table in ("ml_model_events", "ml_online_evaluation"):
            result.extend(self._load_table_rows(table, "governance", "governance_status", title_field="event_id", time_field="created_at", advisory=True))
        return result

    def load_system_evidence(self) -> list[ExplanationEvidence]:
        return []

    def _read_status(self, status_path: str | Path, label: str) -> dict[str, Any]:
        path = Path(status_path)
        if not path.is_absolute():
            path = self.root / path
        if not path.exists():
            self._warn_once(f"missing_status:{label}:{path}", f"missing_status:{label}:{path}")
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            return clean_dict(data)
        except Exception as exc:
            self._warn_once(f"broken_status:{label}:{type(exc).__name__}", f"broken_status:{label}:{exc}")
            return {}

    def _load_table_rows(self, table: str, source: str, evidence_type: str, *, title_field: str, time_field: str, advisory: bool = False, observed: bool = False, estimated: bool = False) -> list[ExplanationEvidence]:
        if not self.db_path.exists():
            self._warn_once(f"missing_db:{self.db_path}", f"missing_db:{self.db_path}")
            return []
        try:
            conn = sqlite3.connect(f"file:{self.db_path.as_posix()}?mode=ro", uri=True, timeout=1.0)
            conn.row_factory = sqlite3.Row
            try:
                exists = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
                if not exists:
                    self._warn_once(f"missing_table:{table}", f"missing_table:{table}")
                    return []
                columns = {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
                order = self._pick_order_field(columns, time_field)
                rows = self._fetch_table_rows(conn, table, order)
                return [self._evidence_from_payload(source, evidence_type, str(dict(row).get(title_field) or table), dict(row), advisory=advisory, observed=observed, estimated=estimated) for row in rows]
            finally:
                conn.close()
        except sqlite3.OperationalError as exc:
            self._warn_once(f"read_table_failed:{table}:{type(exc).__name__}", f"read_table_failed:{table}:{exc}")
            return []
        except Exception as exc:
            self._warn_once(f"read_table_failed:{table}:{type(exc).__name__}", f"read_table_failed:{table}:{exc}")
            return []

    def _pick_order_field(self, columns: set[str], preferred: str | None) -> str | None:
        for candidate in (preferred, "rowid", "updated_at", "created_at", "generated_at", "timestamp", "id"):
            if not candidate:
                continue
            if candidate == "rowid" or candidate in columns:
                return candidate
        return None

    def _fetch_table_rows(self, conn: sqlite3.Connection, table: str, order: str | None) -> list[sqlite3.Row]:
        limit = max(1, self.limit)
        if order:
            try:
                return conn.execute(f"SELECT * FROM {table} ORDER BY {order} DESC LIMIT ?", (limit,)).fetchall()
            except Exception as exc:
                self._warn_once(f"order_fallback:{table}:{order}:{type(exc).__name__}", f"order_fallback:{table}:{order}:{exc}")
        return conn.execute(f"SELECT * FROM {table} LIMIT ?", (limit,)).fetchall()

    def _evidence_from_payload(self, source: str, evidence_type: str, title: Any, payload: Any, *, advisory: bool = False, observed: bool = False, estimated: bool = False, confidence: str = "unknown") -> ExplanationEvidence:
        data = clean_dict(payload)
        timestamp = str(data.get("timestamp") or data.get("created_at") or data.get("updated_at") or data.get("generated_at") or utc_now_iso())
        ident = str(data.get("evidence_id") or data.get("metric_id") or data.get("alert_id") or data.get("diagnosis_id") or data.get("strategy_id") or data.get("report_id") or data.get("summary_id") or data.get("decision_id") or data.get("estimate_id") or title or timestamp)
        summary = str(data.get("summary") or data.get("message") or data.get("status") or data.get("recommendation") or data.get("mode") or title or evidence_type)
        risk_flags = clean_list(data.get("risk_flags") or json_loads_safe(data.get("risk_flags_json"), []))
        reason_codes = clean_list(data.get("reason_codes") or json_loads_safe(data.get("reason_codes_json"), []))
        related_ids = [str(item) for item in clean_list(data.get("related_ids") or [])]
        for key in ("decision_id", "alpha_id", "run_id", "strategy_id", "plan_id", "replay_run_id", "request_id"):
            if data.get(key):
                related_ids.append(str(data.get(key)))
        return ExplanationEvidence(
            evidence_id=f"{source}:{evidence_type}:{ident}",
            source=source,
            evidence_type=evidence_type,
            title=str(title or evidence_type),
            summary=summary,
            confidence=str(data.get("confidence") or confidence or "unknown"),
            observed=observed,
            estimated=estimated,
            advisory=advisory,
            timestamp=timestamp,
            related_ids=related_ids,
            reason_codes=[str(item) for item in reason_codes],
            risk_flags=[str(item) for item in risk_flags],
            raw_payload=data,
        )

    def _system_evidence(self, title: str, summary: str, *, risk_flags: list[str] | None = None, reason_codes: list[str] | None = None) -> ExplanationEvidence:
        return ExplanationEvidence(source="system", evidence_type="system_status", title=title, summary=summary, confidence="unknown", advisory=True, timestamp=utc_now_iso(), reason_codes=list(reason_codes or []), risk_flags=list(risk_flags or []), raw_payload={"warnings": list(self.warnings), "unavailable_sources": self._unavailable_sources()})

    def _unavailable_sources(self) -> list[str]:
        values: list[str] = []
        for warning in self.warnings:
            if warning.startswith("missing_status:"):
                parts = warning.split(":", 3)
                if len(parts) >= 3:
                    values.append(parts[1])
            elif warning.startswith(("missing_table:", "missing_db:")):
                values.append(warning.split(":", 1)[0])
        return sorted(set(values))

    def _warn_once(self, key: str, message: str) -> None:
        if key in self._warning_keys:
            return
        self._warning_keys.add(key)
        self._warn(message)

    def _warn(self, message: str) -> None:
        self.warnings.append(message)
        try:
            if self.logger is not None:
                self.logger.warning("explanation evidence loader: %s", message)
        except Exception:
            pass
