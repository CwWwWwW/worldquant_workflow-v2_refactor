from __future__ import annotations

from wq_workflow.observability.alert_schema import AlertEvent
from wq_workflow.observability.health_diagnosis import HealthDiagnosisService
from wq_workflow.observability.schema import ObservabilityMetric, ObservabilitySourceStatus


def test_observability_health_diagnosis_statuses():
    svc = HealthDiagnosisService()
    metric = ObservabilityMetric(source="workflow", metric_name="workflow.recent_success_count", value=1)
    healthy = svc.diagnose([metric], [ObservabilitySourceStatus(source="workflow", available=True)], [], [])
    assert any(d.area == "workflow" and d.status == "healthy" for d in healthy.diagnoses)
    warning = AlertEvent(alert_name="source_stale", source="workflow", severity="warning", reason_codes=["source_stale"])
    watch = svc.diagnose([metric], [ObservabilitySourceStatus(source="workflow", available=True)], [], [warning])
    assert any(d.area == "workflow" and d.status in {"watch", "degraded"} for d in watch.diagnoses)
    critical = svc.diagnose([metric], [ObservabilitySourceStatus(source="database", available=False)], [], [AlertEvent(alert_name="database_unavailable", source="database", severity="critical", reason_codes=["database_unavailable"])])
    assert critical.overall_status == "critical"
    assert all(d.to_dict()["auto_action_allowed"] is False for d in critical.diagnoses)
