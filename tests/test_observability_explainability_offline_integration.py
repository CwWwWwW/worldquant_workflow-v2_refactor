from __future__ import annotations

import json
from types import SimpleNamespace

from wq_workflow.observability.evidence_loader import ExplanationEvidenceLoader


def test_offline_integration_snapshot_replay_counterfactual(tmp_path):
    status = tmp_path / "runtime/status"; status.mkdir(parents=True)
    (status / "decision_snapshot_status.json").write_text(json.dumps({"snapshot_count": 1}), encoding="utf-8")
    (status / "offline_replay_report.json").write_text(json.dumps({"metrics": [{"metric_id": "r1"}]}), encoding="utf-8")
    (status / "counterfactual_report.json").write_text(json.dumps({"recent_estimates": [{"estimate_id": "c1"}]}), encoding="utf-8")
    cfg = SimpleNamespace(storage_db_path=str(tmp_path / "workflow.db"), decision_snapshot_status_path="runtime/status/decision_snapshot_status.json", offline_replay_status_path="runtime/status/offline_replay_report.json", counterfactual_status_path="runtime/status/counterfactual_report.json", observability_explanation_recent_limit=1000)
    evidence = ExplanationEvidenceLoader(config=cfg, root=tmp_path).load_all_evidence()
    assert any(e.source == "decision_snapshot" for e in evidence)
    assert any(e.source == "offline_replay" and e.advisory for e in evidence)
    assert any(e.source == "counterfactual" and e.estimated and not e.observed for e in evidence)
