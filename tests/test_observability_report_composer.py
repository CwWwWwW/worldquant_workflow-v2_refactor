from __future__ import annotations

from wq_workflow.observability.explanation_schema import DecisionTrace, ExplanationEvidence, RunExplanation
from wq_workflow.observability.report_composer import ReportComposer


def test_report_composer_daily_and_stage():
    trace = DecisionTrace(decision_type="budget_recommendation", evidence=[ExplanationEvidence(source="strategy_budget", evidence_type="budget_allocation")])
    run = RunExplanation(run_summary="summary", decision_traces=[trace], budget_summary={"advisory_only": True}, limitations=["counterfactual evidence is estimated, not observed"])
    composer = ReportComposer()
    daily = composer.compose_daily_report(run, date="2026-05-26")
    stage = composer.compose_stage_summary(run)
    assert daily.date == "2026-05-26"
    assert "7A" in stage.completed_substages and "7B" in stage.completed_substages and "7C" in stage.completed_substages
    assert "run_explain_report.json" in stage.generated_reports
    assert daily.to_dict()["auto_action_allowed"] is False
    assert stage.to_dict()["auto_action_allowed"] is False
