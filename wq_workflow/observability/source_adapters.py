from __future__ import annotations

import csv
import sqlite3
import shutil
from pathlib import Path
from typing import Any

from wq_workflow import paths

from .status_reader import StatusReader
from .utils import clean_dict, safe_float_value, safe_int_value, utc_now_iso


def _resolve(root: Path, value: str | Path | None, default: str) -> Path:
    candidate = Path(value or default)
    return candidate if candidate.is_absolute() else root / candidate


class BaseSourceAdapter:
    source = "unknown"

    def __init__(self, *, config: Any | None = None, db_path: str | Path | None = None, root: str | Path | None = None, reader: StatusReader | None = None) -> None:
        self.config = config
        self.root = Path(root or paths.ROOT)
        configured_db = db_path or getattr(config, "storage_db_path", "runtime/db/workflow.db")
        self.db_path = _resolve(self.root, configured_db, "runtime/db/workflow.db")
        self.reader = reader or StatusReader()
        self.max_age = safe_int_value(getattr(config, "observability_status_max_age_seconds", 86400), 86400)

    def collect(self) -> dict[str, Any]:
        raise NotImplementedError

    def _status(self, path: str | Path) -> tuple[bool, dict[str, Any], list[str], bool, str | None]:
        target = _resolve(self.root, path, str(path))
        ok, payload, warnings = self.reader.read_status_if_exists(target)
        return ok, payload, warnings, self.reader.is_stale(target, self.max_age), self.reader.get_mtime_iso(target)

    def _connect_readonly(self) -> tuple[sqlite3.Connection | None, list[str]]:
        if not self.db_path.exists():
            return None, [f"workflow_db_missing:{self.db_path}"]
        try:
            conn = sqlite3.connect(f"file:{self.db_path.as_posix()}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            return conn, []
        except Exception as exc:
            return None, [f"workflow_db_read_failed:{exc}"]

    def _table_exists(self, conn: sqlite3.Connection, table: str) -> bool:
        row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
        return row is not None

    def _count_table(self, conn: sqlite3.Connection, table: str, warnings: list[str]) -> int:
        try:
            if not self._table_exists(conn, table):
                warnings.append(f"table_missing:{table}")
                return 0
            row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
            return int(row[0] if row else 0)
        except Exception as exc:
            warnings.append(f"table_count_failed:{table}:{exc}")
            return 0

    def _metric(self, name: str, value: Any, *, source: str | None = None, metric_type: str = "gauge", unit: str | None = "count", tags: dict[str, Any] | None = None) -> dict[str, Any]:
        return {"source": source or self.source, "metric_name": name, "metric_type": metric_type, "value": value, "unit": unit, "tags": clean_dict(tags or {})}

    def _result(self, *, metrics: list[dict[str, Any]], warnings: list[str], available: bool, status_path: str | None = None, table_names: list[str] | None = None, last_updated_at: str | None = None, is_stale: bool = False, raw_payload: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            "source": self.source,
            "available": bool(available),
            "metrics": metrics,
            "status_path": status_path,
            "table_names": table_names or [],
            "last_updated_at": last_updated_at,
            "is_stale": bool(is_stale),
            "warnings": warnings,
            "raw_payload": clean_dict(raw_payload or {}),
        }


class WorkflowStatusAdapter(BaseSourceAdapter):
    source = "workflow"

    def collect(self) -> dict[str, Any]:
        warnings: list[str] = []
        metrics: list[dict[str, Any]] = []
        table_names = ["alpha_runs", "candidate_pool", "known_alphas", "iterations"]
        conn, db_warnings = self._connect_readonly()
        warnings.extend(db_warnings)
        db_available = conn is not None
        metrics.append(self._metric("workflow.db_available", db_available, metric_type="status", unit=None))
        if conn is not None:
            try:
                total = 0
                for table in table_names:
                    count = self._count_table(conn, table, warnings)
                    total += count
                metrics.append(self._metric("workflow.iteration_count", total))
            finally:
                conn.close()
        iter_path = self.root / "iteration_log.csv"
        if iter_path.exists():
            try:
                with iter_path.open("r", encoding="utf-8-sig", newline="") as fh:
                    rows = list(csv.DictReader(fh))[-100:]
                success = sum(1 for row in rows if str(row.get("success", "")).lower() in {"1", "true", "yes", "ok", "success"})
                metrics.append(self._metric("workflow.recent_success_count", success))
                metrics.append(self._metric("workflow.recent_failure_count", max(0, len(rows) - success)))
            except Exception as exc:
                warnings.append(f"iteration_log_read_failed:{exc}")
        else:
            warnings.append("iteration_log_missing")
        log_path = self.root / "workflow.log"
        last = self.reader.get_mtime_iso(log_path) if log_path.exists() else None
        if last:
            metrics.append(self._metric("workflow.last_run_at", last, metric_type="timestamp", unit=None))
        else:
            warnings.append("workflow_log_missing")
        runtime_path = getattr(self.config, "legacy_runtime_state_path", "runtime/status/runtime_state.json")
        ok, runtime_payload, runtime_warnings, runtime_stale, runtime_mtime = self._status(runtime_path)
        warnings.extend(runtime_warnings)
        metrics.append(self._metric("workflow.runtime_state_available", ok, metric_type="status", unit=None))
        metrics.append(self._metric("workflow.runtime_state_stale", runtime_stale, metric_type="status", unit=None))
        if runtime_payload:
            metrics.append(self._metric("workflow.latest_state", str(runtime_payload.get("current_state") or "unknown"), metric_type="status", unit=None))
            if runtime_payload.get("current_iteration") is not None:
                metrics.append(self._metric("workflow.latest_iteration", safe_int_value(runtime_payload.get("current_iteration"), 0)))
        recent_events = []
        recent_path = _resolve(self.root, getattr(self.config, "legacy_recent_events_path", "runtime/status/recent_events.jsonl"), "runtime/status/recent_events.jsonl")
        try:
            from wq_workflow.legacy_bridge.recent_events import RecentEventReader

            recent_events = RecentEventReader(recent_path).summarize_recent(limit=50)
        except Exception as exc:
            warnings.append(f"recent_events_read_failed:{exc}")
        metrics.append(self._metric("workflow.recent_event_count", len(recent_events)))
        recent_error_count = sum(1 for event in recent_events if str(event.get("severity") or event.get("level") or "").lower() in {"error", "critical"})
        metrics.append(self._metric("workflow.recent_error_count", recent_error_count))
        updated = runtime_mtime or last
        return self._result(metrics=metrics, warnings=warnings, available=db_available or iter_path.exists() or log_path.exists() or ok, table_names=table_names, last_updated_at=updated, raw_payload={"db_path": str(self.db_path), "runtime_state": runtime_payload, "recent_event_count": len(recent_events)})


class MLMetricsAdapter(BaseSourceAdapter):
    source = "ml"

    def collect(self) -> dict[str, Any]:
        warnings: list[str] = []
        metrics: list[dict[str, Any]] = []
        tables = ["ml_model_registry", "ml_prediction_audit", "ml_training_samples"]
        conn, db_warnings = self._connect_readonly()
        warnings.extend(db_warnings)
        if conn is not None:
            try:
                metrics.append(self._metric("ml.model_count", self._count_table(conn, "ml_model_registry", warnings)))
                active = 0
                if self._table_exists(conn, "ml_model_registry"):
                    active = int(conn.execute("SELECT COUNT(*) FROM ml_model_registry WHERE COALESCE(is_active,0) != 0").fetchone()[0])
                metrics.append(self._metric("ml.active_model_count", active))
                metrics.append(self._metric("ml.prediction_count", self._count_table(conn, "ml_prediction_audit", warnings)))
                failed = 0
                if self._table_exists(conn, "ml_prediction_audit"):
                    failed = int(conn.execute("SELECT COUNT(*) FROM ml_prediction_audit WHERE lower(COALESCE(final_decision,'')) IN ('failed','error','blocked')").fetchone()[0])
                metrics.append(self._metric("ml.failed_prediction_count", failed))
                metrics.append(self._metric("ml.training_sample_count", self._count_table(conn, "ml_training_samples", warnings)))
            finally:
                conn.close()
        status_path = getattr(self.config, "ml_status_path", "runtime/status/ml_status.json")
        ok, payload, status_warnings, stale, mtime = self._status(status_path)
        warnings.extend(status_warnings)
        return self._result(metrics=metrics, warnings=warnings, available=bool(conn is not None or ok), status_path=str(status_path), table_names=tables, last_updated_at=mtime, is_stale=stale, raw_payload={"status": payload})


class GovernanceMetricsAdapter(BaseSourceAdapter):
    source = "governance"

    def collect(self) -> dict[str, Any]:
        warnings: list[str] = []
        metrics: list[dict[str, Any]] = []
        tables = ["ml_model_events", "ml_online_evaluation"]
        conn, db_warnings = self._connect_readonly()
        warnings.extend(db_warnings)
        if conn is not None:
            try:
                metrics.append(self._metric("governance.model_disable_count", self._count_table(conn, "ml_model_events", warnings)))
                metrics.append(self._metric("governance.blocked_decision_count", self._count_table(conn, "ml_online_evaluation", warnings)))
            finally:
                conn.close()
        status_path = getattr(self.config, "governance_status_path", "runtime/status/governance_status.json")
        ok, payload, status_warnings, stale, mtime = self._status(status_path)
        warnings.extend(status_warnings)
        enabled = bool(getattr(self.config, "enable_learning_governance", True))
        metrics.append(self._metric("governance.enabled", enabled, metric_type="status", unit=None))
        metrics.append(self._metric("governance.warning_count", len(warnings)))
        return self._result(metrics=metrics, warnings=warnings, available=bool(conn is not None or ok or enabled), status_path=str(status_path), table_names=tables, last_updated_at=mtime, is_stale=stale, raw_payload={"status": payload})


class ExperimentMetricsAdapter(BaseSourceAdapter):
    source = "experiment"

    def collect(self) -> dict[str, Any]:
        warnings: list[str] = []
        metrics: list[dict[str, Any]] = []
        tables = ["experiment_plans", "experiment_assignments", "experiment_results", "experiment_summaries", "experiment_budget_plans"]
        conn, db_warnings = self._connect_readonly()
        warnings.extend(db_warnings)
        if conn is not None:
            try:
                for table, metric in (
                    ("experiment_plans", "experiment.plan_count"),
                    ("experiment_assignments", "experiment.assignment_count"),
                    ("experiment_results", "experiment.result_count"),
                    ("experiment_summaries", "experiment.summary_count"),
                    ("experiment_budget_plans", "experiment.budget_plan_count"),
                ):
                    metrics.append(self._metric(metric, self._count_table(conn, table, warnings)))
            finally:
                conn.close()
        status_path = getattr(self.config, "experiment_status_path", "runtime/status/experiment_report.json")
        ok, payload, status_warnings, stale, mtime = self._status(status_path)
        warnings.extend(status_warnings)
        return self._result(metrics=metrics, warnings=warnings, available=bool(conn is not None or ok), status_path=str(status_path), table_names=tables, last_updated_at=mtime, is_stale=stale, raw_payload={"status": payload})


class OfflineMetricsAdapter(BaseSourceAdapter):
    source = "offline_replay"

    def collect(self) -> dict[str, Any]:
        warnings: list[str] = []
        metrics: list[dict[str, Any]] = []
        tables = ["decision_snapshots", "decision_outcomes", "offline_replay_runs", "offline_replay_policy_decisions", "counterfactual_estimates"]
        conn, db_warnings = self._connect_readonly()
        warnings.extend(db_warnings)
        if conn is not None:
            try:
                for table, metric, source in (
                    ("decision_snapshots", "offline.decision_snapshot_count", "offline_replay"),
                    ("decision_outcomes", "offline.decision_outcome_count", "offline_replay"),
                    ("offline_replay_runs", "offline.replay_run_count", "offline_replay"),
                    ("offline_replay_policy_decisions", "offline.replay_policy_decision_count", "offline_replay"),
                    ("counterfactual_estimates", "offline.counterfactual_estimate_count", "counterfactual"),
                ):
                    metrics.append(self._metric(metric, self._count_table(conn, table, warnings), source=source))
                insufficient = 0
                if self._table_exists(conn, "counterfactual_estimates"):
                    insufficient = int(conn.execute("SELECT COUNT(*) FROM counterfactual_estimates WHERE COALESCE(estimated_not_observed,0) != 0 OR lower(COALESCE(confidence,''))='insufficient'").fetchone()[0])
                metrics.append(self._metric("offline.counterfactual_insufficient_count", insufficient, source="counterfactual"))
            finally:
                conn.close()
        status_paths = [
            getattr(self.config, "decision_snapshot_status_path", "runtime/status/decision_snapshot_status.json"),
            getattr(self.config, "offline_replay_status_path", "runtime/status/offline_replay_report.json"),
            getattr(self.config, "counterfactual_status_path", "runtime/status/counterfactual_report.json"),
        ]
        payloads: dict[str, Any] = {}
        stale = False
        mtime = None
        ok_any = False
        for status_path in status_paths:
            ok, payload, status_warnings, item_stale, item_mtime = self._status(status_path)
            ok_any = ok_any or ok
            stale = stale or item_stale
            mtime = item_mtime or mtime
            payloads[str(status_path)] = payload
            warnings.extend(status_warnings)
        return self._result(metrics=metrics, warnings=warnings, available=bool(conn is not None or ok_any), status_path=";".join(str(p) for p in status_paths), table_names=tables, last_updated_at=mtime, is_stale=stale, raw_payload={"statuses": payloads})


class StrategyMetricsAdapter(BaseSourceAdapter):
    source = "strategy"

    def collect(self) -> dict[str, Any]:
        warnings: list[str] = []
        metrics: list[dict[str, Any]] = []
        tables = ["strategy_profiles", "strategy_scores", "strategy_portfolio_states", "strategy_budget_allocations"]
        conn, db_warnings = self._connect_readonly()
        warnings.extend(db_warnings)
        if conn is not None:
            try:
                metrics.append(self._metric("strategy.profile_count", self._count_table(conn, "strategy_profiles", warnings), source="strategy"))
                metrics.append(self._metric("strategy.score_count", self._count_table(conn, "strategy_scores", warnings), source="strategy"))
                states = self._count_table(conn, "strategy_portfolio_states", warnings)
                champion = challenger = limited = 0
                if self._table_exists(conn, "strategy_portfolio_states"):
                    champion = int(conn.execute("SELECT COUNT(*) FROM strategy_portfolio_states WHERE lower(COALESCE(recommended_state,current_state,''))='champion'").fetchone()[0])
                    challenger = int(conn.execute("SELECT COUNT(*) FROM strategy_portfolio_states WHERE lower(COALESCE(recommended_state,current_state,''))='challenger'").fetchone()[0])
                    limited = int(conn.execute("SELECT COUNT(*) FROM strategy_portfolio_states WHERE lower(COALESCE(recommended_state,current_state,''))='limited_active'").fetchone()[0])
                metrics.append(self._metric("strategy.champion_count", champion, source="strategy_portfolio"))
                metrics.append(self._metric("strategy.challenger_count", challenger, source="strategy_portfolio"))
                metrics.append(self._metric("strategy.limited_active_count", limited, source="strategy_portfolio"))
                budget_count = self._count_table(conn, "strategy_budget_allocations", warnings)
                metrics.append(self._metric("strategy.budget_allocation_count", budget_count, source="strategy_budget"))
                total = 0.0
                if self._table_exists(conn, "strategy_budget_allocations"):
                    row = conn.execute("SELECT SUM(COALESCE(suggested_ratio,0)) FROM strategy_budget_allocations").fetchone()
                    total = safe_float_value(row[0] if row else 0.0, 0.0)
                metrics.append(self._metric("strategy.budget_total_suggested_ratio", total, source="strategy_budget", metric_type="ratio", unit="ratio"))
            finally:
                conn.close()
        status_paths = [
            getattr(self.config, "strategy_scoreboard_status_path", "runtime/status/strategy_scoreboard.json"),
            getattr(self.config, "strategy_portfolio_status_path", "runtime/status/strategy_portfolio_report.json"),
            getattr(self.config, "strategy_budget_status_path", "runtime/status/strategy_budget_report.json"),
        ]
        payloads: dict[str, Any] = {}
        stale = False
        mtime = None
        ok_any = False
        for status_path in status_paths:
            ok, payload, status_warnings, item_stale, item_mtime = self._status(status_path)
            ok_any = ok_any or ok
            stale = stale or item_stale
            mtime = item_mtime or mtime
            payloads[str(status_path)] = payload
            warnings.extend(status_warnings)
        return self._result(metrics=metrics, warnings=warnings, available=bool(conn is not None or ok_any), status_path=";".join(str(p) for p in status_paths), table_names=tables, last_updated_at=mtime, is_stale=stale, raw_payload={"statuses": payloads})


class SystemMetricsAdapter(BaseSourceAdapter):
    source = "system"

    def collect(self) -> dict[str, Any]:
        warnings: list[str] = []
        metrics: list[dict[str, Any]] = []
        runtime = self.root / "runtime"
        status_dir = runtime / "status"
        logs = self.root / "logs"
        metrics.append(self._metric("system.status_file_count", len(list(status_dir.glob("*.json"))) if status_dir.exists() else 0))
        metrics.append(self._metric("system.workflow_db_exists", self.db_path.exists(), metric_type="status", unit=None))
        metrics.append(self._metric("system.runtime_exists", runtime.exists(), metric_type="status", unit=None))
        metrics.append(self._metric("system.log_exists", logs.exists(), metric_type="status", unit=None))
        try:
            usage = shutil.disk_usage(self.root)
            metrics.append(self._metric("system.disk_free_mb", round(usage.free / 1024 / 1024, 3), unit="mb"))
            metrics.append(self._metric("system.disk_total_mb", round(usage.total / 1024 / 1024, 3), unit="mb"))
        except Exception as exc:
            warnings.append(f"disk_usage_failed:{exc}")
        metrics.append(self._metric("system.current_time", utc_now_iso(), metric_type="timestamp", unit=None))
        return self._result(metrics=metrics, warnings=warnings, available=True, table_names=[], last_updated_at=utc_now_iso(), raw_payload={"root": str(self.root)})
