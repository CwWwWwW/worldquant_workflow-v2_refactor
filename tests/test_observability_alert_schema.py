from __future__ import annotations

import json

from wq_workflow.observability.alert_schema import AlertEvent, AlertRule, DriftRule, DriftSignal, HealthDiagnosis, HealthDiagnosisReport


def test_observability_alert_schema_roundtrip_json_safe():
    items = [
        DriftRule(rule_id="r1", metric_name="workflow.recent_failure_count", threshold=0.5),
        DriftSignal(signal_id="s1", rule_id="r1", source="workflow", metric_name="workflow.recent_failure_count", current_value=2, baseline_value=1, triggered=True, reason_codes=["x"]),
        AlertRule(rule_id="a1", alert_name="source_unavailable", condition_type="source_unavailable"),
        AlertEvent(alert_id="e1", rule_id="a1", alert_name="source_unavailable", source="workflow", reason_codes=["source_unavailable"]),
        HealthDiagnosis(diagnosis_id="d1", area="workflow", auto_action_allowed=True),
    ]
    for item in items:
        data = item.to_dict()
        json.dumps(data)
        assert data.get("created_at", "").endswith("+00:00")
    assert HealthDiagnosis.from_dict(items[-1].to_dict()).to_dict()["auto_action_allowed"] is False
    report = HealthDiagnosisReport(report_id="hr1", diagnoses=[items[-1]], alert_events=[items[3]], drift_signals=[items[1]])
    data = HealthDiagnosisReport.from_dict(report.to_dict()).to_dict()
    assert data["mode"] == "advisory"
    assert data["diagnoses"][0]["auto_action_allowed"] is False
