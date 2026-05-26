from __future__ import annotations

from wq_workflow.observability.explanation_schema import ExplanationEvidence
from wq_workflow.observability.run_explainer import RunExplainer


def test_run_explainer_rules():
    evidence = [
        ExplanationEvidence(source="health_diagnosis", evidence_type="diagnosis", title="overall", summary="critical", raw_payload={"status": "critical"}),
        ExplanationEvidence(source="observability_alerts", evidence_type="alert", title="sc", risk_flags=["high_sc_risk"]),
        ExplanationEvidence(source="governance", evidence_type="governance_status", summary="governance block"),
        ExplanationEvidence(source="system", evidence_type="system_status", risk_flags=["missing_source"]),
        ExplanationEvidence(source="counterfactual", evidence_type="counterfactual_estimate"),
        ExplanationEvidence(source="strategy_budget", evidence_type="budget_allocation"),
    ]
    run = RunExplainer().explain(evidence, [])
    assert any("critical diagnosis" in x for x in run.key_findings)
    assert "review_sc_risk" in run.recommended_human_checks
    assert "review_governance_blocks" in run.recommended_human_checks
    assert any("stale or missing" in x for x in run.limitations)
    assert any("estimated" in x for x in run.limitations)
    assert run.to_dict()["auto_action_allowed"] is False
    empty = RunExplainer().explain([], [])
    assert "insufficient" in empty.run_summary
