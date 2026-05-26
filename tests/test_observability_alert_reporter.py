from __future__ import annotations

import json

from wq_workflow.observability.alert_reporter import AlertReporter
from wq_workflow.observability.alert_schema import AlertEvent, DriftSignal


def test_observability_alert_reporter_writes_and_backs_up(tmp_path):
    target = tmp_path / "runtime/status/observability_alerts.json"
    target.parent.mkdir(parents=True)
    target.write_text("{broken", encoding="utf-8")
    result = AlertReporter(target, root=tmp_path).update([AlertEvent(alert_id="e1", alert_name="x", source="workflow", reason_codes=["x"])], [DriftSignal(signal_id="s1", source="workflow", metric_name="m", triggered=True)])
    assert result["ok"] is True and result["backups"]
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert {"alerts", "drift_signals", "summary", "warnings"} <= set(payload)
