from __future__ import annotations

import json
import sqlite3
from types import SimpleNamespace

from wq_workflow.data.migrations import initialize_refactor_tables
from wq_workflow.observability.evidence_loader import ExplanationEvidenceLoader


def _cfg(tmp_path):
    return SimpleNamespace(storage_db_path=str(tmp_path / "workflow.db"), observability_metrics_status_path="runtime/status/observability_metrics.json", observability_alerts_status_path="runtime/status/observability_alerts.json", observability_diagnosis_status_path="runtime/status/health_diagnosis.json", strategy_budget_status_path="runtime/status/strategy_budget_report.json", counterfactual_status_path="runtime/status/counterfactual_report.json", observability_explanation_recent_limit=1000)


def test_evidence_loader_missing_broken_and_typed_sources(tmp_path):
    root = tmp_path
    status = root / "runtime/status"
    status.mkdir(parents=True)
    (status / "observability_metrics.json").write_text(json.dumps({"metrics": [{"metric_id": "m1", "metric_name": "workflow.ok", "value": 1}]}), encoding="utf-8")
    (status / "observability_alerts.json").write_text(json.dumps({"alerts": [{"alert_id": "a1", "alert_name": "sc_risk_high", "severity": "warning"}]}), encoding="utf-8")
    (status / "health_diagnosis.json").write_text(json.dumps({"diagnoses": [{"diagnosis_id": "d1", "area": "overall", "status": "critical", "summary": "critical"}]}), encoding="utf-8")
    (status / "strategy_budget_report.json").write_text(json.dumps({"allocations": [{"allocation_id": "b1", "strategy_id": "s1"}]}), encoding="utf-8")
    (status / "counterfactual_report.json").write_text(json.dumps({"recent_estimates": [{"estimate_id": "c1", "confidence": "medium"}]}), encoding="utf-8")
    (status / "strategy_scoreboard.json").write_text("{broken", encoding="utf-8")
    conn = sqlite3.connect(tmp_path / "workflow.db")
    initialize_refactor_tables(conn)
    conn.execute("INSERT INTO observability_metrics(metric_id, source, metric_name, metric_type, value_json, timestamp) VALUES('m2','workflow','workflow.fail','counter','2','t')")
    conn.commit(); conn.close()
    evidence = ExplanationEvidenceLoader(config=_cfg(tmp_path), root=root).load_all_evidence()
    assert any(e.source == "observability_metrics" for e in evidence)
    assert any(e.evidence_type == "alert" for e in evidence)
    assert any(e.evidence_type == "diagnosis" for e in evidence)
    assert any(e.source == "strategy_budget" and e.advisory for e in evidence)
    assert any(e.source == "counterfactual" and e.estimated and not e.observed for e in evidence)
