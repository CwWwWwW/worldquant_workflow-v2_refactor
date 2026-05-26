from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from wq_workflow import paths

from .dashboard_schema import DashboardSourceStatus
from .log_summarizer import LogSummarizer


DEFAULT_STATUS_FILES: dict[str, str] = {
    "strategy_scoreboard": "runtime/status/strategy_scoreboard.json",
    "strategy_portfolio": "runtime/status/strategy_portfolio_report.json",
    "strategy_budget": "runtime/status/strategy_budget_report.json",
    "observability_metrics": "runtime/status/observability_metrics.json",
    "observability_alerts": "runtime/status/observability_alerts.json",
    "health_diagnosis": "runtime/status/health_diagnosis.json",
    "run_explain_report": "runtime/status/run_explain_report.json",
    "daily_observability_report": "runtime/status/daily_observability_report.json",
    "stage7_summary_report": "runtime/status/stage7_summary_report.json",
    "decision_snapshot_status": "runtime/status/decision_snapshot_status.json",
    "offline_replay_report": "runtime/status/offline_replay_report.json",
    "counterfactual_report": "runtime/status/counterfactual_report.json",
    "experiment_report": "runtime/status/experiment_report.json",
    "governance_status": "runtime/status/governance_status.json",
    "ml_status": "runtime/status/ml_status.json",
    "runtime_state": "runtime/status/runtime_state.json",
}

DEFAULT_LOG_FILES = [
    "logs/workflow_state.jsonl",
    "workflow.log",
    "iteration_log.csv",
    "logs/workflow.log",
]


class DashboardReadonlySources:
    def __init__(
        self,
        *,
        root: str | Path | None = None,
        status_files: dict[str, str | Path] | None = None,
        stale_after_seconds: int = 86_400,
        db_path: str | Path | None = None,
        log_paths: list[str | Path] | None = None,
    ) -> None:
        self.root = Path(root or paths.ROOT)
        self.status_files = dict(status_files or DEFAULT_STATUS_FILES)
        self.stale_after_seconds = max(0, int(stale_after_seconds))
        self.db_path = self._resolve(db_path or "runtime/db/workflow.db")
        self.log_paths = [self._resolve(p) for p in (log_paths or DEFAULT_LOG_FILES)]
        self.log_summarizer = LogSummarizer()

    def read_status_payloads(self) -> tuple[dict[str, Any], list[DashboardSourceStatus]]:
        payloads: dict[str, Any] = {}
        statuses: list[DashboardSourceStatus] = []
        for name, raw_path in self.status_files.items():
            status, payload = self.read_json_source(name, self._resolve(raw_path))
            statuses.append(status)
            payloads[name] = payload
        return payloads, statuses

    def read_json_source(self, source: str, path: str | Path) -> tuple[DashboardSourceStatus, dict[str, Any]]:
        p = Path(path)
        warnings: list[str] = []
        if not p.exists():
            warnings.append("missing")
            return DashboardSourceStatus(source=source, available=False, stale=False, path=str(p), warning_count=1, warnings=warnings), {}
        try:
            stat = p.stat()
            stale = self.stale_after_seconds > 0 and (time.time() - stat.st_mtime) > self.stale_after_seconds
            text = p.read_text(encoding="utf-8-sig")
            value = json.loads(text)
            if not isinstance(value, dict):
                warnings.append("json_not_object")
                value = {"value": value}
            updated_at = str(value.get("updated_at") or value.get("generated_at") or _mtime_iso(stat.st_mtime))
            if stale:
                warnings.append("stale")
            summary = _summarize_payload(value)
            return (
                DashboardSourceStatus(
                    source=source,
                    available=True,
                    stale=stale,
                    path=str(p),
                    updated_at=updated_at,
                    warning_count=len(warnings),
                    summary=summary,
                    warnings=warnings,
                ),
                value,
            )
        except Exception as exc:
            warnings.append(f"read_failed:{type(exc).__name__}:{exc}")
            return DashboardSourceStatus(source=source, available=False, stale=False, path=str(p), warning_count=len(warnings), warnings=warnings), {}


    def read_recent_events_summary(self, *, limit: int = 20) -> tuple[DashboardSourceStatus, dict[str, Any]]:
        path = self._resolve("runtime/status/recent_events.jsonl")
        try:
            from wq_workflow.legacy_bridge.recent_events import RecentEventReader

            events = RecentEventReader(path).summarize_recent(limit=limit)
            available = path.exists()
            warnings = [] if available else ["missing"]
            return (
                DashboardSourceStatus(
                    source="recent_events",
                    available=available,
                    stale=False,
                    path=str(path),
                    warning_count=len(warnings),
                    summary={"event_count": len(events)},
                    warnings=warnings,
                ),
                {"events": events},
            )
        except Exception as exc:
            warning = f"read_failed:{type(exc).__name__}:{exc}"
            return DashboardSourceStatus(source="recent_events", available=False, path=str(path), warning_count=1, warnings=[warning]), {"events": []}

    def read_legacy_evidence_summary(self, *, limit: int = 200) -> tuple[DashboardSourceStatus, dict[str, Any]]:
        path = self._resolve("runtime/status/legacy_learning_evidence.jsonl")
        try:
            from wq_workflow.legacy_bridge.evidence import LegacyLearningEvidenceReader

            reader = LegacyLearningEvidenceReader(path)
            by_type = reader.summarize_by_type(limit=limit)
            recent = reader.summarize_recent(limit=min(20, limit))
            available = path.exists()
            warnings = [] if available else ["missing"]
            return (
                DashboardSourceStatus(
                    source="legacy_learning_evidence",
                    available=available,
                    stale=False,
                    path=str(path),
                    warning_count=len(warnings),
                    summary={"type_count": len(by_type), "recent_count": len(recent)},
                    warnings=warnings,
                ),
                {"by_type": by_type, "recent": recent},
            )
        except Exception as exc:
            warning = f"read_failed:{type(exc).__name__}:{exc}"
            return DashboardSourceStatus(source="legacy_learning_evidence", available=False, path=str(path), warning_count=1, warnings=[warning]), {"by_type": {}, "recent": []}

    def read_db_summary(self, *, enabled: bool = True) -> tuple[DashboardSourceStatus, dict[str, Any]]:
        if not enabled:
            return DashboardSourceStatus(source="workflow_db", available=False, path=str(self.db_path), warnings=["disabled"], warning_count=1), {}
        if not self.db_path.exists():
            return DashboardSourceStatus(source="workflow_db", available=False, path=str(self.db_path), warnings=["missing"], warning_count=1), {}
        conn: sqlite3.Connection | None = None
        try:
            uri = f"file:{self.db_path.as_posix()}?mode=ro"
            conn = sqlite3.connect(uri, uri=True, timeout=1.0)
            conn.row_factory = sqlite3.Row
            tables = {str(row[0]) for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            summary: dict[str, Any] = {"tables": len(tables)}
            for table in (
                "ml_model_registry",
                "ml_training_samples",
                "ml_prediction_audit",
                "model_safety_reports",
                "strategy_registry",
                "strategy_budget_allocations",
                "observability_metrics",
                "observability_alert_events",
                "observability_health_reports",
                "observability_decision_traces",
                "decision_snapshots",
                "offline_replay_runs",
                "counterfactual_estimates",
                "alpha_runs",
            ):
                if table in tables:
                    summary[f"{table}_count"] = _count(conn, table)
            summary["latest_prediction_at"] = _latest(conn, tables, "ml_prediction_audit", ("created_at", "timestamp"))
            summary["latest_alpha_run_at"] = _latest(conn, tables, "alpha_runs", ("created_at", "updated_at", "timestamp"))
            return DashboardSourceStatus(source="workflow_db", available=True, path=str(self.db_path), summary=summary), summary
        except sqlite3.OperationalError as exc:
            warning = f"sqlite_warning:{exc}"
            return DashboardSourceStatus(source="workflow_db", available=False, path=str(self.db_path), warning_count=1, warnings=[warning]), {}
        except Exception as exc:
            warning = f"db_read_failed:{type(exc).__name__}:{exc}"
            return DashboardSourceStatus(source="workflow_db", available=False, path=str(self.db_path), warning_count=1, warnings=[warning]), {}
        finally:
            try:
                if conn is not None:
                    conn.close()
            except Exception:
                pass

    def read_log_summary(self, *, enabled: bool = True, max_bytes: int = 200_000, limit: int = 20) -> tuple[DashboardSourceStatus, dict[str, Any]]:
        if not enabled:
            return DashboardSourceStatus(source="logs", available=False, warnings=["disabled"], warning_count=1), {"events": [], "errors": []}
        combined = []
        paths_read = []
        warnings = []
        for path in self.log_paths:
            text = self.log_summarizer.read_tail(path, max_bytes=max_bytes)
            if text:
                combined.append(text)
                paths_read.append(str(path))
            elif path.exists():
                warnings.append(f"empty_or_unreadable:{path.name}")
        all_text = "\n".join(combined)
        events = self.log_summarizer.extract_recent_events(all_text, limit=limit)
        errors = self.log_summarizer.extract_error_summaries(all_text, limit=5)
        available = bool(paths_read)
        return (
            DashboardSourceStatus(
                source="logs",
                available=available,
                path=";".join(paths_read) if paths_read else None,
                warning_count=len(warnings),
                summary={"event_count": len(events), "error_count": len(errors)},
                warnings=warnings,
            ),
            {"events": events, "errors": errors},
        )

    def _resolve(self, path: str | Path) -> Path:
        p = Path(path)
        return p if p.is_absolute() else self.root / p


def _mtime_iso(value: float) -> str:
    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()


def _summarize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for key, value in list(payload.items())[:12]:
        if isinstance(value, list):
            summary[key] = {"type": "list", "count": len(value)}
        elif isinstance(value, dict):
            summary[key] = {"type": "dict", "keys": list(value.keys())[:8]}
        else:
            summary[key] = value
    return summary


def _count(conn: sqlite3.Connection, table: str) -> int:
    try:
        row = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()
        return int(row[0] if row else 0)
    except Exception:
        return 0


def _latest(conn: sqlite3.Connection, tables: set[str], table: str, columns: tuple[str, ...]) -> str | None:
    if table not in tables:
        return None
    table_columns = {str(row[1]) for row in conn.execute(f'PRAGMA table_info("{table}")').fetchall()}
    for column in columns:
        if column in table_columns:
            row = conn.execute(f'SELECT "{column}" FROM "{table}" WHERE "{column}" IS NOT NULL ORDER BY "{column}" DESC LIMIT 1').fetchone()
            if row and row[0] not in (None, ""):
                return str(row[0])
    return None
