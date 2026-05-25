from wq_workflow.offline.counterfactual_features import CounterfactualFeatureBuilder
from wq_workflow.offline.schema import CounterfactualRequest, DecisionAction


def test_features_similarity_bounds_and_weights():
    b=CounterfactualFeatureBuilder(); a=DecisionAction(action_id='a', action_type='arm', metadata={'operator_family':'op','behavior_family':'b'})
    fp1=b.combined_fingerprint(CounterfactualRequest(decision_id='d', decision_type='experiment_arm_selection', target_action=a, features={'operator_family':'op'}, context={'behavior_family':'b'}))
    fp2=dict(fp1)
    assert b.action_fingerprint(a)==b.action_fingerprint(a.to_dict())
    assert 0 <= b.similarity(fp1, fp2) <= 1
    diff=dict(fp1); diff['decision_type']='budget_plan_selection'; diff['action_type']='budget'
    assert b.similarity(fp1, diff) < b.similarity(fp1, fp2)
