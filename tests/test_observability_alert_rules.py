from __future__ import annotations

from wq_workflow.observability.alert_rules import AlertRuleEngine
from wq_workflow.observability.alert_schema import DriftSignal
from wq_workflow.observability.schema import ObservabilityMetric, ObservabilitySourceStatus


def test_observability_alert_rules_sources_drift_warning_disk():
    engine = AlertRuleEngine()
    statuses = [ObservabilitySourceStatus(source="workflow", available=False), ObservabilitySourceStatus(source="platform", available=True, is_stale=True, warnings=["x"])]
    signals = [DriftSignal(rule_id="platform_failure_spike", source="platform", metric_name="platform.failure_count", current_value=3, triggered=True, reason_codes=["platform_failure_spike"])]
    metrics = [ObservabilityMetric(source="system", metric_name="system.free_disk_mb", value=1)]
    alerts = engine.evaluate(signals, statuses, metrics)
    names = {a.alert_name for a in alerts}
    assert {"source_unavailable", "source_stale", "platform_failure_spike", "disk_low"} <= names
    assert all(a.status == "open" and a.reason_codes for a in alerts)
