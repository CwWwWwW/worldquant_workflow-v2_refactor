from __future__ import annotations

import json
from types import SimpleNamespace

from wq_workflow.observability.evidence_loader import ExplanationEvidenceLoader
from wq_workflow.observability.run_explainer import RunExplainer


def test_alert_integration_critical_and_stale_limitations(tmp_path):
    status = tmp_path / "runtime/status"; status.mkdir(parents=True)
    (status / "observability_alerts.json").write_text(json.dumps({"alerts": [{"alert_id": "a", "alert_name": "source_stale", "severity": "warning", "reason_codes": ["stale_source"]}]}), encoding="utf-8")
    (status / "health_diagnosis.json").write_text(json.dumps({"diagnoses": [{"diagnosis_id": "d", "area": "overall", "status": "critical", "summary": "critical"}]}), encoding="utf-8")
    cfg = SimpleNamespace(storage_db_path=str(tmp_path / "workflow.db"), observability_alerts_status_path="runtime/status/observability_alerts.json", observability_diagnosis_status_path="runtime/status/health_diagnosis.json", observability_explanation_recent_limit=1000)
    evidence = ExplanationEvidenceLoader(config=cfg, root=tmp_path).load_all_evidence()
    run = RunExplainer().explain(evidence, [])
    assert any(e.evidence_type == "alert" for e in evidence)
    assert any(e.evidence_type == "diagnosis" for e in evidence)
    assert any("critical diagnosis" in x for x in run.key_findings)
    assert any("stale or missing" in x for x in run.limitations)
