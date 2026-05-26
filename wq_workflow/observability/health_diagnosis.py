from __future__ import annotations

from typing import Any

from .alert_schema import AlertEvent, DriftSignal, HealthDiagnosis, HealthDiagnosisReport
from .schema import ObservabilityMetric, ObservabilitySourceStatus
from .utils import clean_dict, utc_now_iso


DIAGNOSIS_AREAS = [
    "workflow",
    "platform",
    "parsing",
    "sc_risk",
    "ml",
    "governance",
    "experiment",
    "offline_replay",
    "counterfactual",
    "strategy",
    "strategy_budget",
    "database",
    "system",
    "overall",
]


AREA_SOURCES = {
    "workflow": {"workflow"},
    "platform": {"platform"},
    "parsing": {"platform", "workflow"},
    "sc_risk": {"strategy", "strategy_budget"},
    "ml": {"ml"},
    "governance": {"governance"},
    "experiment": {"experiment"},
    "offline_replay": {"offline_replay"},
    "counterfactual": {"counterfactual"},
    "strategy": {"strategy", "strategy_portfolio"},
    "strategy_budget": {"strategy_budget"},
    "database": {"database"},
    "system": {"system"},
}


AREA_ACTIONS = {
    "workflow": "inspect_logs",
    "platform": "review_platform_status",
    "parsing": "inspect_logs",
    "sc_risk": "review_sc_risk",
    "ml": "inspect_logs",
    "governance": "review_governance_blocks",
    "experiment": "refresh_observability_metrics",
    "offline_replay": "refresh_observability_metrics",
    "counterfactual": "refresh_observability_metrics",
    "strategy": "inspect_strategy_budget_report",
    "strategy_budget": "inspect_strategy_budget_report",
    "database": "verify_runtime_db",
    "system": "inspect_logs",
    "overall": "no_action_required",
}


class HealthDiagnosisService:
    def __init__(self, *, config: Any | None = None) -> None:
        self.config = config

    def diagnose(
        self,
        metrics: list[ObservabilityMetric],
        source_statuses: list[ObservabilitySourceStatus],
        drift_signals: list[DriftSignal],
        alert_events: list[AlertEvent],
    ) -> HealthDiagnosisReport:
        safe_metrics = [ObservabilityMetric.from_dict(metric) for metric in list(metrics or [])]
        safe_statuses = [ObservabilitySourceStatus.from_dict(status) for status in list(source_statuses or [])]
        safe_signals = [DriftSignal.from_dict(signal) for signal in list(drift_signals or [])]
        safe_alerts = [AlertEvent.from_dict(alert) for alert in list(alert_events or [])]
        diagnoses = [self.diagnose_area(area, safe_metrics, safe_statuses, safe_signals, safe_alerts) for area in DIAGNOSIS_AREAS if area != "overall"]
        overall_status = self.compute_overall_status(diagnoses)
        generated_at = utc_now_iso()
        overall = HealthDiagnosis(
            diagnosis_id=f"diagnosis:overall:{generated_at}",
            area="overall",
            status=overall_status,
            severity=self._severity_for_status(overall_status),
            summary=f"Overall observability health is {overall_status}",
            evidence_metrics=[],
            alert_ids=[alert.alert_id for alert in safe_alerts],
            drift_signal_ids=[signal.signal_id for signal in safe_signals if signal.triggered],
            recommended_action="no_action_required" if overall_status == "healthy" else "inspect_logs",
            auto_action_allowed=False,
            created_at=generated_at,
            raw_payload={"mode": "advisory"},
        )
        diagnoses.append(overall)
        return HealthDiagnosisReport(
            report_id=f"health_diagnosis_report:{generated_at}",
            generated_at=generated_at,
            mode="advisory",
            overall_status=overall_status,
            diagnoses=diagnoses,
            alert_events=safe_alerts,
            drift_signals=safe_signals,
            summary=self.summarize(diagnoses, safe_alerts, safe_signals),
            warnings=[],
            raw_payload={"mode": "advisory"},
        )

    def diagnose_area(
        self,
        area: str,
        metrics: list[ObservabilityMetric],
        source_statuses: list[ObservabilitySourceStatus],
        drift_signals: list[DriftSignal],
        alert_events: list[AlertEvent],
    ) -> HealthDiagnosis:
        sources = AREA_SOURCES.get(area, {area})
        area_metrics = [metric for metric in metrics if metric.source in sources or metric.metric_name.startswith(tuple(f"{src}." for src in sources))]
        area_statuses = [status for status in source_statuses if status.source in sources]
        area_alerts = [alert for alert in alert_events if self._belongs_to_area(area, alert.source, alert.alert_name, alert.metric_name)]
        area_signals = [signal for signal in drift_signals if self._belongs_to_area(area, signal.source, signal.rule_id, signal.metric_name)]
        critical_alert = any(alert.triggered and alert.severity == "critical" for alert in area_alerts)
        critical_signal = any(signal.triggered and signal.severity == "critical" for signal in area_signals)
        warning_count = sum(1 for alert in area_alerts if alert.triggered and alert.severity == "warning") + sum(1 for signal in area_signals if signal.triggered and signal.severity == "warning")
        stale = any(status.is_stale for status in area_statuses)
        unavailable = any(not status.available for status in area_statuses)
        if not area_metrics and not area_statuses and not area_alerts and not area_signals:
            status = "unknown"
        elif critical_alert or area == "database" and unavailable or area == "system" and any(alert.alert_name == "disk_low" for alert in area_alerts):
            status = "critical"
        elif unavailable or critical_signal or warning_count > 1:
            status = "degraded"
        elif warning_count == 1 or stale:
            status = "watch"
        else:
            status = "healthy"
        severity = self._severity_for_status(status)
        action = "no_action_required" if status == "healthy" else AREA_ACTIONS.get(area, "inspect_logs")
        summary = self._summary(area, status, stale=stale, unavailable=unavailable, warning_count=warning_count)
        created_at = utc_now_iso()
        return HealthDiagnosis(
            diagnosis_id=f"diagnosis:{area}:{created_at}",
            area=area,
            status=status,
            severity=severity,
            summary=summary,
            evidence_metrics=[metric.metric_name for metric in area_metrics],
            alert_ids=[alert.alert_id for alert in area_alerts if alert.triggered],
            drift_signal_ids=[signal.signal_id for signal in area_signals if signal.triggered],
            recommended_action=action,
            auto_action_allowed=False,
            created_at=created_at,
            raw_payload=clean_dict({"source_count": len(area_statuses), "mode": "advisory"}),
        )

    def compute_overall_status(self, diagnoses: list[HealthDiagnosis]) -> str:
        statuses = [HealthDiagnosis.from_dict(item).status for item in diagnoses or []]
        if not statuses or all(status == "unknown" for status in statuses):
            return "unknown"
        if "critical" in statuses:
            return "critical"
        if "degraded" in statuses:
            return "degraded"
        if "watch" in statuses:
            return "watch"
        if "healthy" in statuses:
            return "healthy"
        return "unknown"

    def summarize(self, diagnoses: list[HealthDiagnosis], alerts: list[AlertEvent], drift_signals: list[DriftSignal]) -> dict[str, Any]:
        status_counts = {"healthy_count": 0, "watch_count": 0, "degraded_count": 0, "critical_count": 0, "unknown_count": 0}
        for diagnosis in diagnoses or []:
            status = HealthDiagnosis.from_dict(diagnosis).status
            key = f"{status}_count"
            status_counts[key] = status_counts.get(key, 0) + 1
        return {
            **status_counts,
            "alert_count": len([alert for alert in alerts or [] if AlertEvent.from_dict(alert).triggered]),
            "critical_alert_count": len([alert for alert in alerts or [] if AlertEvent.from_dict(alert).severity == "critical" and AlertEvent.from_dict(alert).triggered]),
            "triggered_drift_count": len([signal for signal in drift_signals or [] if DriftSignal.from_dict(signal).triggered]),
        }

    def _belongs_to_area(self, area: str, source: str, name: str | None, metric_name: str | None) -> bool:
        sources = AREA_SOURCES.get(area, {area})
        text = " ".join(str(part or "") for part in (source, name, metric_name)).lower()
        if source in sources:
            return True
        if area == "parsing":
            return "parse" in text or "parsing" in text
        if area == "sc_risk":
            return "sc_risk" in text or "high_sc" in text
        if area == "strategy_budget":
            return "budget" in text
        return area in text

    def _severity_for_status(self, status: str) -> str:
        if status == "critical":
            return "critical"
        if status in {"watch", "degraded"}:
            return "warning"
        return "info"

    def _summary(self, area: str, status: str, *, stale: bool, unavailable: bool, warning_count: int) -> str:
        if status == "healthy":
            return f"{area} appears healthy"
        if status == "unknown":
            return f"{area} health is unknown due to missing observability evidence"
        if unavailable:
            return f"{area} source is unavailable"
        if stale:
            return f"{area} source is stale"
        if warning_count:
            return f"{area} has {warning_count} advisory warning(s)"
        return f"{area} is {status}"
