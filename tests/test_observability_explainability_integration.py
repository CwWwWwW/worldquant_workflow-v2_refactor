from __future__ import annotations

import json
from types import SimpleNamespace

from wq_workflow.observability.explainability_service import ExplainabilityService


def test_explainability_integration_fake_status_reports(tmp_path):
    status = tmp_path / "runtime/status"
    status.mkdir(parents=True)
    (status / "observability_metrics.json").write_text(json.dumps({"metrics": [{"metric_id": "m", "metric_name": "workflow.success", "value": 1}]}), encoding="utf-8")
    (status / "observability_alerts.json").write_text(json.dumps({"alerts": [{"alert_id": "a", "alert_name": "watch", "severity": "warning"}]}), encoding="utf-8")
    (status / "health_diagnosis.json").write_text(json.dumps({"diagnoses": [{"diagnosis_id": "d", "area": "overall", "status": "watch"}]}), encoding="utf-8")
    cfg = SimpleNamespace(storage_db_path=str(tmp_path / "workflow.db"), enable_run_explainability=False, observability_explainability_auto_run=False, observability_explainability_fail_open=True, observability_explanation_recent_limit=1000)
    result = ExplainabilityService(config=cfg, root=tmp_path).generate_explanations()
    assert result["ok"] is True
    assert (status / "run_explain_report.json").exists()
    assert (status / "daily_observability_report.json").exists()
    assert (status / "stage7_summary_report.json").exists()
