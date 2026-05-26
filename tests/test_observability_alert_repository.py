from __future__ import annotations

import sqlite3

from wq_workflow.observability.alert_repository import AlertRepository
from wq_workflow.observability.alert_schema import AlertEvent, AlertRule, DriftRule, DriftSignal


def test_observability_alert_repository_crud(tmp_path):
    repo = AlertRepository(conn=sqlite3.connect(tmp_path / "workflow.db"))
    assert repo.initialize()["ok"] is True
    assert repo.save_drift_rule(DriftRule(rule_id="r1", metric_name="m"))
    assert repo.list_drift_rules()[0].rule_id == "r1"
    assert repo.save_drift_signal(DriftSignal(signal_id="s1", rule_id="r1", source="workflow", metric_name="m", reason_codes=["x"]))
    assert repo.list_drift_signals()[0].signal_id == "s1"
    assert repo.save_alert_rule(AlertRule(rule_id="a1", alert_name="n"))
    assert repo.list_alert_rules()[0].rule_id == "a1"
    assert repo.save_alert_event(AlertEvent(alert_id="e1", rule_id="a1", alert_name="n", source="workflow", reason_codes=["x"]))
    assert repo.list_alert_events(source="workflow")[0].alert_id == "e1"
