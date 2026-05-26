from __future__ import annotations

import json

from wq_workflow.observability.explanation_schema import DailyRunReport, DecisionTrace, ExplanationEvidence, RunExplanation, StageSummaryReport


def test_explanation_schema_roundtrip_json_safe_and_forced_flags():
    ev = ExplanationEvidence(source="counterfactual", evidence_type="counterfactual_estimate", title="cf", summary="estimated", observed=True, estimated=False, advisory=False)
    data = ev.to_dict()
    assert data["estimated"] is True and data["observed"] is False and data["advisory"] is True
    assert ExplanationEvidence.from_dict(data).to_dict()["source"] == "counterfactual"
    budget = ExplanationEvidence(source="strategy_budget", evidence_type="budget_allocation").to_dict()
    assert budget["advisory"] is True
    trace = DecisionTrace(decision_type="strategy_selection", evidence=[ev])
    run = RunExplanation(decision_traces=[trace], auto_action_allowed=True)
    daily = DailyRunReport(auto_action_allowed=True)
    stage = StageSummaryReport(auto_action_allowed=True)
    for obj in (trace, run, daily, stage):
        payload = obj.to_dict()
        json.dumps(payload)
    assert run.to_dict()["auto_action_allowed"] is False
    assert daily.to_dict()["auto_action_allowed"] is False
    assert stage.to_dict()["auto_action_allowed"] is False
    assert "+00:00" in ev.to_dict()["timestamp"]
