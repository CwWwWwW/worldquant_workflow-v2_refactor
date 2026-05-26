from __future__ import annotations

from copy import deepcopy

from wq_workflow.observability.decision_trace import DecisionTraceBuilder
from wq_workflow.observability.explanation_schema import ExplanationEvidence


def test_decision_trace_builder_groups_without_mutation():
    evidence = [
        ExplanationEvidence(source="strategy_scoreboard", evidence_type="strategy_score", title="s"),
        ExplanationEvidence(source="strategy_budget", evidence_type="budget_allocation", title="b"),
        ExplanationEvidence(source="governance", evidence_type="governance_status", summary="governance block"),
        ExplanationEvidence(source="counterfactual", evidence_type="counterfactual_estimate"),
        ExplanationEvidence(source="health_diagnosis", evidence_type="diagnosis", summary="critical"),
    ]
    before = [deepcopy(e.to_dict()) for e in evidence]
    traces = DecisionTraceBuilder().build_traces(evidence)
    types = {t.decision_type for t in traces}
    assert {"strategy_selection", "budget_recommendation", "governance_decision", "counterfactual_estimate", "workflow_run"} <= types
    assert any("counterfactual" in " ".join(t.warnings) for t in traces)
    assert before == [e.to_dict() for e in evidence]
