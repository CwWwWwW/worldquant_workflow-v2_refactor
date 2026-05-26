from __future__ import annotations

import sqlite3

from wq_workflow.observability.alert_schema import AlertEvent, DriftSignal, HealthDiagnosis, HealthDiagnosisReport
from wq_workflow.observability.diagnosis_repository import DiagnosisRepository


def test_observability_diagnosis_repository_crud(tmp_path):
    repo = DiagnosisRepository(conn=sqlite3.connect(tmp_path / "workflow.db"))
    assert repo.initialize()["ok"] is True
    diag = HealthDiagnosis(diagnosis_id="d1", area="workflow", recommended_action="inspect_logs", auto_action_allowed=True)
    assert repo.save_diagnosis(diag)
    assert repo.list_diagnoses(area="workflow")[0].to_dict()["auto_action_allowed"] is False
    report = HealthDiagnosisReport(report_id="r1", diagnoses=[diag], alert_events=[AlertEvent(alert_id="a1", alert_name="n", source="workflow")], drift_signals=[DriftSignal(signal_id="s1")])
    assert repo.save_report(report)
    assert repo.get_latest_report().report_id == "r1"
