from __future__ import annotations

import json

from wq_workflow.observability.alert_schema import HealthDiagnosis, HealthDiagnosisReport
from wq_workflow.observability.diagnosis_reporter import DiagnosisReporter


def test_observability_diagnosis_reporter_writes_and_forces_no_auto_action(tmp_path):
    target = tmp_path / "runtime/status/health_diagnosis.json"
    target.parent.mkdir(parents=True)
    target.write_text("{broken", encoding="utf-8")
    report = HealthDiagnosisReport(report_id="r1", overall_status="watch", diagnoses=[HealthDiagnosis(area="workflow", auto_action_allowed=True)])
    result = DiagnosisReporter(target, root=tmp_path).update(report)
    assert result["ok"] is True and result["backups"]
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["diagnoses"][0]["auto_action_allowed"] is False
