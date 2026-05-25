from wq_workflow.offline.counterfactual_metrics import CounterfactualMetricsCalculator
from wq_workflow.offline.schema import CounterfactualEvidence, CounterfactualRequest


def test_metrics_weighted_and_risk_boundaries():
    calc=CounterfactualMetricsCalculator(min_evidence=2,min_effective_evidence=1,high_sc_abs_max_threshold=0.7,low_success_rate_threshold=0.2)
    req=CounterfactualRequest(request_id='r', decision_id='d', min_evidence=2, context={'baseline_reward':0.0})
    ev=[CounterfactualEvidence(similarity_score=1,reward=1,success=True,platform_sc_abs_max=0.8,quality_passed=True), CounterfactualEvidence(similarity_score=1,reward=3,success=False,platform_sc_abs_max=0.8,quality_passed=False)]
    est=calc.estimate_from_evidence(req, ev)
    assert est.estimated_reward==2
    assert est.estimated_success_rate==0.5
    assert est.estimated_quality_pass_rate==0.5
    assert est.estimated_not_observed is True
    assert est.verdict=='high_risk_estimate'
    low=calc.estimate_from_evidence(CounterfactualRequest(request_id='r2',decision_id='d2',min_evidence=3), ev)
    assert low.verdict=='insufficient_evidence'
