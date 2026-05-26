from __future__ import annotations

from types import SimpleNamespace

from wq_workflow.observability.evidence_loader import ExplanationEvidenceLoader
from wq_workflow.observability.run_explainer import RunExplainer


def test_missing_status_warns_once_and_report_limitations(tmp_path):
    cfg = SimpleNamespace(
        storage_db_path=str(tmp_path / "workflow.db"),
        strategy_scoreboard_status_path="runtime/status/strategy_scoreboard.json",
        strategy_portfolio_status_path="runtime/status/strategy_portfolio_report.json",
        strategy_budget_status_path="runtime/status/strategy_budget_report.json",
        governance_status_path="runtime/status/governance_status.json",
        observability_explanation_recent_limit=10,
    )
    loader = ExplanationEvidenceLoader(config=cfg, root=tmp_path)

    assert loader._read_status("runtime/status/strategy_scoreboard.json", "strategy_scoreboard") == {}
    assert loader._read_status("runtime/status/strategy_scoreboard.json", "strategy_scoreboard") == {}
    matching = [w for w in loader.warnings if w.startswith("missing_status:strategy_scoreboard:")]
    assert len(matching) == 1

    evidence = loader.load_all_evidence()
    assert evidence
    assert any(item.source == "system" and "source_unavailable" in item.reason_codes for item in evidence)
    report = RunExplainer().explain(evidence, [])
    assert any("missing" in item.lower() for item in report.limitations)
