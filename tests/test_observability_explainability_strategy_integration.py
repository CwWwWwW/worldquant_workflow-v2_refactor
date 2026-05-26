from __future__ import annotations

import json
from types import SimpleNamespace

from wq_workflow.observability.evidence_loader import ExplanationEvidenceLoader
from wq_workflow.observability.run_explainer import RunExplainer


def test_strategy_integration_evidence_explained_advisory(tmp_path):
    status = tmp_path / "runtime/status"; status.mkdir(parents=True)
    (status / "strategy_scoreboard.json").write_text(json.dumps({"scores": [{"strategy_id": "s1", "confidence": "medium"}]}), encoding="utf-8")
    (status / "strategy_portfolio_report.json").write_text(json.dumps({"strategy_states": [{"strategy_id": "s1", "current_state": "champion"}]}), encoding="utf-8")
    (status / "strategy_budget_report.json").write_text(json.dumps({"allocations": [{"strategy_id": "s1", "suggested_ratio": 0.4}]}), encoding="utf-8")
    cfg = SimpleNamespace(storage_db_path=str(tmp_path / "workflow.db"), strategy_scoreboard_status_path="runtime/status/strategy_scoreboard.json", strategy_portfolio_status_path="runtime/status/strategy_portfolio_report.json", strategy_budget_status_path="runtime/status/strategy_budget_report.json", observability_explanation_recent_limit=1000)
    evidence = ExplanationEvidenceLoader(config=cfg, root=tmp_path).load_all_evidence()
    assert any(e.source == "strategy_scoreboard" for e in evidence)
    assert any(e.source == "strategy_portfolio" for e in evidence)
    assert any(e.source == "strategy_budget" and e.advisory for e in evidence)
    run = RunExplainer().explain(evidence, [])
    assert any("budget" in x.lower() for x in run.limitations + run.key_findings)
