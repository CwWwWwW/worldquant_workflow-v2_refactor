from wq_workflow.offline.schema import CounterfactualEvidence, CounterfactualEstimate, CounterfactualRequest, CounterfactualSummary, DecisionAction


def test_counterfactual_schema_roundtrip_json_safe():
    req=CounterfactualRequest(request_id='r', decision_id='d', target_action=DecisionAction(action_id='a'), features={'x':1}, context={'y':2})
    assert CounterfactualRequest.from_dict(req.to_dict()).features['x']==1
    ev=CounterfactualEvidence(evidence_id='e', request_id='r', source_decision_id='s', similarity_score=0.8, reason_codes=['observed'])
    assert CounterfactualEvidence.from_dict(ev.to_dict()).reason_codes==['observed']
    est=CounterfactualEstimate(estimate_id='est', request_id='r', decision_id='d', risk_flags=['high_sc_risk'])
    assert CounterfactualEstimate.from_dict(est.to_dict()).estimated_not_observed is True
    summ=CounterfactualSummary(summary_id='s', request_count=1)
    assert CounterfactualSummary.from_dict(summ.to_dict()).request_count==1
    assert '+00:00' in req.created_at
