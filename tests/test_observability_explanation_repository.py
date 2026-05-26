from __future__ import annotations

from wq_workflow.observability.explanation_repository import ExplanationRepository
from wq_workflow.observability.explanation_schema import DailyRunReport, DecisionTrace, ExplanationEvidence, RunExplanation, StageSummaryReport


def test_explanation_repository_save_list_latest(tmp_path):
    repo = ExplanationRepository(db_path=tmp_path / "workflow.db")
    assert repo.initialize()["ok"] is True
    ev = ExplanationEvidence(evidence_id="e1", source="strategy_budget", evidence_type="budget_allocation")
    assert repo.save_evidence(ev)
    assert repo.save_evidence_batch([ev])
    assert repo.list_evidence(source="strategy_budget")[0].evidence_id == "e1"
    trace = DecisionTrace(trace_id="t1", decision_type="budget_recommendation", evidence=[ev])
    assert repo.save_trace(trace)
    assert repo.list_traces(decision_type="budget_recommendation")[0].trace_id == "t1"
    run = RunExplanation(explanation_id="r1", decision_traces=[trace])
    daily = DailyRunReport(report_id="d1", date="2026-05-26")
    stage = StageSummaryReport(report_id="s1")
    assert repo.save_run_explanation(run) and repo.save_daily_report(daily) and repo.save_stage_summary(stage)
    assert repo.get_latest_run_explanation().explanation_id == "r1"
    assert repo.get_latest_daily_report().report_id == "d1"
    assert repo.get_latest_stage_summary().report_id == "s1"
    assert len(repo.list_evidence()) == 1
