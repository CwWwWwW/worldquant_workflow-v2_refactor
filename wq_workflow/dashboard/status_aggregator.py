from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from wq_workflow import paths

from .dashboard_schema import (
    DashboardMLStatus,
    DashboardObservabilityStatus,
    DashboardRuntimeStatus,
    DashboardSnapshot,
    DashboardSourceStatus,
    DashboardStrategyStatus,
)
from .readonly_sources import DashboardReadonlySources


class DashboardStatusAggregator:
    def __init__(
        self,
        *,
        root: str | Path | None = None,
        include_db: bool = True,
        include_logs: bool = True,
        stale_after_seconds: int = 86_400,
        sources: DashboardReadonlySources | None = None,
    ) -> None:
        self.root = Path(root or paths.ROOT)
        self.include_db = include_db
        self.include_logs = include_logs
        self.sources = sources or DashboardReadonlySources(root=self.root, stale_after_seconds=stale_after_seconds)
        self._payloads: dict[str, Any] = {}
        self._source_statuses: list[DashboardSourceStatus] = []
        self._db_summary: dict[str, Any] = {}
        self._log_summary: dict[str, Any] = {"events": [], "errors": []}
        self._bridge_events: dict[str, Any] = {"events": []}
        self._legacy_evidence_summary: dict[str, Any] = {"by_type": {}, "recent": []}

    def build_snapshot(self) -> DashboardSnapshot:
        generated_at = _now()
        payloads, statuses = self.sources.read_status_payloads()
        db_status, db_summary = self.sources.read_db_summary(enabled=self.include_db)
        log_status, log_summary = self.sources.read_log_summary(enabled=self.include_logs)
        bridge_event_status, bridge_events = self.sources.read_recent_events_summary(limit=20)
        evidence_status, evidence_summary = self.sources.read_legacy_evidence_summary(limit=200)
        self._payloads = payloads
        self._db_summary = db_summary
        self._log_summary = log_summary
        self._bridge_events = bridge_events
        self._legacy_evidence_summary = evidence_summary
        self._source_statuses = statuses + [db_status, log_status, bridge_event_status, evidence_status]
        global_warnings = []
        for status in self._source_statuses:
            global_warnings.extend([f"{status.source}:{w}" for w in status.warnings])
        return DashboardSnapshot(
            generated_at=generated_at,
            runtime=self.load_runtime_status(generated_at=generated_at),
            ml=self.load_ml_status(),
            strategy=self.load_strategy_status(),
            observability=self.load_observability_status(),
            sources=self.load_source_statuses(),
            global_warnings=global_warnings[-50:],
            raw_payload={
                "status_payload_keys": sorted(payloads.keys()),
                "db_summary": db_summary,
                "log_errors": log_summary.get("errors", []),
                "legacy_evidence_summary": evidence_summary,
            },
        )

    def load_runtime_status(self, *, generated_at: str | None = None) -> DashboardRuntimeStatus:
        events = self.get_recent_events(limit=20)
        last = events[-1] if events else {}
        runtime_state = self._payloads.get("runtime_state") if isinstance(self._payloads.get("runtime_state"), dict) else {}
        bridge_available = bool(runtime_state)
        state = _normalize_state(str(runtime_state.get("current_state") or last.get("state") or "UNKNOWN"))
        pid = _read_pid(self.root / "logs" / "workflow_active.pid")
        workflow_running = runtime_state.get("workflow_running") if "workflow_running" in runtime_state else (_process_running(pid) if pid else False)
        if not events and not workflow_running and not bridge_available:
            state = "IDLE"
        return DashboardRuntimeStatus(
            generated_at=generated_at or _now(),
            workflow_running=workflow_running,
            current_phase=str(runtime_state.get("current_phase") or _phase_from_payloads(self._payloads) or "") or None,
            current_template=str(runtime_state.get("current_template") or _first_event_value(events, "template") or "") or None,
            current_alpha_id=str(runtime_state.get("current_alpha_id") or _first_event_value(events, "alpha_id") or "") or None,
            current_iteration=_int_or_none(runtime_state.get("current_iteration")) or _first_int_event_value(events, "iteration"),
            current_state=state,
            platform_waiting=runtime_state.get("platform_waiting") if "platform_waiting" in runtime_state else state == "WAIT_RESULT",
            platform_progress=_float_or_none(runtime_state.get("platform_progress")),
            parse_waiting=runtime_state.get("parse_waiting") if "parse_waiting" in runtime_state else state == "PARSE_RESULT",
            parse_status=str(runtime_state.get("parse_status") or "") or None,
            sc_check_status=str(runtime_state.get("sc_check_status") or ("running" if state == "PLATFORM_SC_CHECK" else ("unknown" if state == "UNKNOWN" else "idle"))),
            last_reward=_float_or_none(runtime_state.get("last_reward")),
            last_sc_value=_float_or_none(runtime_state.get("last_sc_value")),
            last_event_at=str(runtime_state.get("last_event_at") or last.get("time") or last.get("timestamp") or "") or None,
            recent_events=events,
            legacy_evidence_summary=self._legacy_evidence_summary.get("by_type", {}) if isinstance(self._legacy_evidence_summary, dict) else {},
            warnings=[] if (events or bridge_available) else ["recent_events_unavailable"],
        )

    def load_ml_status(self) -> DashboardMLStatus:
        ml_payload = self._payloads.get("ml_status") if isinstance(self._payloads.get("ml_status"), dict) else {}
        config_params = _read_ml_config(self.root)
        summary = dict(self._db_summary or {})
        model_count = _first_int(ml_payload, "model_count", "registry_count") or _int_or_none(summary.get("ml_model_registry_count"))
        training_count = _first_int(ml_payload, "training_sample_count") or _sum_counts(summary, "ml_training_samples_count", "sc_training_samples_count", "parent_selection_samples_count", "policy_training_samples_count", "simulator_training_samples_count")
        prediction_count = _first_int(ml_payload, "prediction_count", "prediction_audit_count") or _int_or_none(summary.get("ml_prediction_audit_count"))
        safety = str(ml_payload.get("safety_gate_status") or ml_payload.get("model_safety_status") or ("unknown" if summary.get("model_safety_reports_count") is None else "tracked"))
        return DashboardMLStatus(
            model_enabled=_bool_from_params(config_params, "enable_ml_system", "ENABLE_ML_SYSTEM"),
            active_model_id=str(ml_payload.get("active_model_id") or ml_payload.get("active_model") or "") or None,
            model_count=model_count,
            training_sample_count=training_count,
            prediction_count=prediction_count,
            last_prediction_at=str(ml_payload.get("last_prediction_at") or summary.get("latest_prediction_at") or "") or None,
            safety_gate_status=safety,
            ml_parameters=config_params,
            warnings=_as_str_list(ml_payload.get("warnings")),
        )

    def load_strategy_status(self) -> DashboardStrategyStatus:
        portfolio = self._payloads.get("strategy_portfolio") if isinstance(self._payloads.get("strategy_portfolio"), dict) else {}
        budget = self._payloads.get("strategy_budget") if isinstance(self._payloads.get("strategy_budget"), dict) else {}
        states = _list_from_any(portfolio.get("strategy_states") or portfolio.get("states") or portfolio.get("portfolio"))
        allocations = _list_from_any(budget.get("allocations") or budget.get("budget_allocations"))
        champion = None
        counts = {"challenger": 0, "limited_active": 0, "shadow": 0, "disabled": 0}
        high_risk = 0
        for row in states:
            role = str(row.get("current_state") or row.get("role") or row.get("status") or "").lower()
            sid = str(row.get("strategy_id") or row.get("id") or "")
            if "champion" in role and not champion:
                champion = sid
            for key in counts:
                if key in role:
                    counts[key] += 1
            flags = " ".join(map(str, row.get("risk_flags") or row.get("reason_codes") or []))
            if "risk" in flags.lower() or "high_sc" in flags.lower():
                high_risk += 1
        slim_allocations = [_slim_dict(row, max_keys=8) for row in allocations[:10]]
        total = 0.0
        seen = False
        for row in allocations:
            value = row.get("suggested_ratio", row.get("ratio", row.get("current_budget")))
            try:
                total += float(value)
                seen = True
            except Exception:
                pass
        return DashboardStrategyStatus(
            champion=champion or str(portfolio.get("champion") or "") or None,
            challenger_count=counts["challenger"],
            limited_active_count=counts["limited_active"],
            shadow_count=counts["shadow"],
            disabled_count=counts["disabled"],
            budget_allocations=slim_allocations,
            budget_total_ratio=round(total, 6) if seen else None,
            high_risk_count=high_risk,
            warnings=_as_str_list(portfolio.get("warnings")) + _as_str_list(budget.get("warnings")),
        )

    def load_observability_status(self) -> DashboardObservabilityStatus:
        by_source = {status.source: status for status in self._source_statuses}
        alerts = self._payloads.get("observability_alerts") if isinstance(self._payloads.get("observability_alerts"), dict) else {}
        diagnosis = self._payloads.get("health_diagnosis") if isinstance(self._payloads.get("health_diagnosis"), dict) else {}
        run = self._payloads.get("run_explain_report") if isinstance(self._payloads.get("run_explain_report"), dict) else {}
        daily = self._payloads.get("daily_observability_report") if isinstance(self._payloads.get("daily_observability_report"), dict) else {}
        alert_count = _first_int(alerts, "alert_count") or len(_list_from_any(alerts.get("alerts") or alerts.get("alert_events")))
        critical_count = _first_int(alerts, "critical_count") or _count_severity(alerts, "critical")
        warning_count = _first_int(alerts, "warning_count") or _count_severity(alerts, "warning")
        findings = _as_str_list(run.get("key_findings")) + _as_str_list(daily.get("key_findings"))
        checks = _as_str_list(run.get("recommended_human_checks")) + _as_str_list(daily.get("recommended_human_checks"))
        return DashboardObservabilityStatus(
            metrics_available=bool(by_source.get("observability_metrics") and by_source["observability_metrics"].available),
            alerts_available=bool(by_source.get("observability_alerts") and by_source["observability_alerts"].available),
            diagnosis_available=bool(by_source.get("health_diagnosis") and by_source["health_diagnosis"].available),
            explainability_available=bool(by_source.get("run_explain_report") and by_source["run_explain_report"].available),
            overall_health=str(diagnosis.get("overall_status") or diagnosis.get("overall_health") or daily.get("health_status") or "") or None,
            alert_count=alert_count,
            critical_count=critical_count,
            warning_count=warning_count,
            key_findings=_dedupe(findings)[:8],
            recommended_human_checks=_dedupe(checks)[:8],
            warnings=_as_str_list(alerts.get("warnings")) + _as_str_list(diagnosis.get("warnings")) + _as_str_list(run.get("limitations")),
        )

    def load_source_statuses(self) -> list[DashboardSourceStatus]:
        return list(self._source_statuses)

    def get_recent_events(self, limit: int = 20) -> list[dict[str, Any]]:
        bridge_events = self._bridge_events.get("events") if isinstance(self._bridge_events, dict) else []
        if bridge_events:
            return list(bridge_events or [])[-max(1, int(limit)) :]
        events = self._log_summary.get("events") if isinstance(self._log_summary, dict) else []
        return list(events or [])[-max(1, int(limit)) :]

    def get_status(self) -> dict[str, Any]:
        return self.build_snapshot().to_dict()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_pid(path: Path) -> int | None:
    try:
        text = path.read_text(encoding="utf-8-sig").strip()
        return int(text) if text else None
    except Exception:
        return None


def _process_running(pid: int | None) -> bool:
    if not pid or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False
    except Exception:
        return False


def _normalize_state(value: str) -> str:
    upper = (value or "").upper()
    known = ["WAIT_RESULT", "PARSE_RESULT", "PLATFORM_SC_CHECK", "GOVERNANCE_CHECK", "STRATEGY_UPDATE", "REWARD_UPDATE", "CANDIDATE_POOL_UPDATE", "SUCCESS_RESULT", "OBSERVABILITY_READY", "ERROR_FATAL", "ERROR_RECOVERABLE", "GENERATING_TEMPLATE", "SUBMITTING_BACKTEST", "STARTING", "IDLE"]
    for state in known:
        if state in upper:
            return state
    return "UNKNOWN"


def _phase_from_payloads(payloads: dict[str, Any]) -> str | None:
    stage = payloads.get("stage7_summary_report")
    if isinstance(stage, dict):
        return str(stage.get("stage_name") or "phase7-observability")
    return None


def _first_event_value(events: list[dict[str, Any]], key: str) -> str | None:
    for event in reversed(events):
        value = event.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def _first_int_event_value(events: list[dict[str, Any]], key: str) -> int | None:
    for event in reversed(events):
        value = _int_or_none(event.get(key))
        if value is not None:
            return value
    return None


def _read_ml_config(root: Path) -> dict[str, Any]:
    values: dict[str, Any] = {}
    try:
        from wq_workflow import config as cfg

        for name in (
            "ENABLE_ML_SYSTEM",
            "ENABLE_SC_MODEL_PREDICTION",
            "ENABLE_MODEL_LIFECYCLE",
            "ENABLE_REFACTORED_PIPELINE",
            "ENABLE_PARENT_MODEL_DECISION",
            "ENABLE_POLICY_MODEL_DECISION",
            "ENABLE_SIMULATOR_MODEL_SKIP",
            "ENABLE_SC_MODEL_FALLBACK",
            "FORCE_ENABLE_UNSAFE_ML_DECISIONS",
        ):
            values[name] = getattr(cfg, name, None)
    except Exception:
        pass
    config_json = root / "config.json"
    try:
        raw = json.loads(config_json.read_text(encoding="utf-8-sig"))
        if isinstance(raw, dict):
            for key in ("enable_ml", "enable_ml_prediction", "enable_model_registry", "enable_prediction_audit", "enable_refactored_pipeline"):
                if key in raw:
                    values[key] = raw.get(key)
    except Exception:
        pass
    return values


def _bool_from_params(params: dict[str, Any], *keys: str) -> bool | None:
    for key in keys:
        if key in params:
            return bool(params[key])
    return None


def _first_int(payload: dict[str, Any], *keys: str) -> int | None:
    for key in keys:
        value = _int_or_none(payload.get(key))
        if value is not None:
            return value
    return None


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except Exception:
        return None


def _sum_counts(payload: dict[str, Any], *keys: str) -> int | None:
    total = 0
    seen = False
    for key in keys:
        value = _int_or_none(payload.get(key))
        if value is not None:
            total += value
            seen = True
    return total if seen else None


def _as_str_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item not in (None, "")]
    if value in (None, ""):
        return []
    return [str(value)]


def _list_from_any(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def _slim_dict(row: dict[str, Any], *, max_keys: int) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in list(row.items())[:max_keys]:
        if isinstance(value, (dict, list)):
            out[key] = f"{type(value).__name__}[{len(value)}]"
        else:
            out[key] = value
    return out


def _count_severity(payload: dict[str, Any], severity: str) -> int:
    rows = _list_from_any(payload.get("alerts") or payload.get("alert_events"))
    return sum(1 for row in rows if str(row.get("severity") or "").lower() == severity)


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            out.append(value)
    return out


def _float_or_none(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None
