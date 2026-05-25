from tests.counterfactual_test_helpers import cfg, seed_observed, seed_replay_decision
from wq_workflow.offline.counterfactual_evaluator import CounterfactualEvaluator
from wq_workflow.offline.counterfactual_dataset import CounterfactualDatasetLoader
from wq_workflow.offline.schema import CounterfactualRequest, ReplayPolicyDecision


def test_evaluator_request_policy_and_run(tmp_path):
    db=tmp_path/'workflow.db'; action=seed_observed(db); pd=seed_replay_decision(db)
    ev=CounterfactualEvaluator(config=cfg(db), db_path=str(db))
    est=ev.evaluate_request(CounterfactualRequest(request_id='r',decision_id='d',decision_type='experiment_arm_selection',target_action=action,features={'operator_family':'op'},context={'behavior_family':'beh','baseline_reward':0},min_evidence=2))
    assert est.estimated_not_observed and est.evidence_count>=2
    before=pd.to_dict()
    est2=ev.evaluate_policy_decision(pd, CounterfactualDatasetLoader(db_path=db, config=cfg(db)).load_record_for_decision(pd.decision_id))
    assert est2 is not None and pd.to_dict()==before
    assert ev.evaluate_policy_decision(ReplayPolicyDecision(observable_outcome=True)) is None
    assert ev.evaluate_policy_decision(ReplayPolicyDecision(observable_outcome=False, selected_action=None)) is None
    assert ev.evaluate_replay_run('run1')
    assert ev.evaluate_replay_run('missing')==[]
