from __future__ import annotations

from pathlib import Path

from wq_workflow.observability.explanation_schema import DailyRunReport, RunExplanation, StageSummaryReport


def test_explainability_boundaries_static():
    files = [path for path in Path("wq_workflow/observability").glob("*.py") if path.name.startswith(("explanation", "explainability", "evidence_loader", "decision_trace", "run_explainer", "report_composer"))]
    text = "\n".join(path.read_text(encoding="utf-8") for path in files)
    forbidden = ["playwright", "browser", "CandidatePool", "submit_backtest", "hard_takeover", "apply_budget", "auto_action_allowed = True"]
    for item in forbidden:
        assert item not in text
    assert RunExplanation(auto_action_allowed=True).to_dict()["auto_action_allowed"] is False
    assert DailyRunReport(auto_action_allowed=True).to_dict()["auto_action_allowed"] is False
    assert StageSummaryReport(auto_action_allowed=True).to_dict()["auto_action_allowed"] is False
