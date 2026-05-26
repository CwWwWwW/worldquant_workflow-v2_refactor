from __future__ import annotations

import json
from types import SimpleNamespace

from wq_workflow.observability.evidence_loader import ExplanationEvidenceLoader
from wq_workflow.observability.run_explainer import RunExplainer


def test_governance_integration_block_human_check(tmp_path):
    status = tmp_path / "runtime/status"; status.mkdir(parents=True)
    (status / "governance_status.json").write_text(json.dumps({"status": "watch", "summary": "governance block active"}), encoding="utf-8")
    cfg = SimpleNamespace(storage_db_path=str(tmp_path / "workflow.db"), governance_status_path="runtime/status/governance_status.json", observability_explanation_recent_limit=1000)
    evidence = ExplanationEvidenceLoader(config=cfg, root=tmp_path).load_all_evidence()
    run = RunExplainer().explain(evidence, [])
    assert any(e.source == "governance" for e in evidence)
    assert "review_governance_blocks" in run.recommended_human_checks
