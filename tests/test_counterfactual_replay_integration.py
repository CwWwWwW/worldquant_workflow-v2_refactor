from tests.counterfactual_test_helpers import cfg, seed_replay_decision
from wq_workflow.offline.counterfactual_evaluator import CounterfactualEvaluator
from wq_workflow.offline.counterfactual_repository import CounterfactualRepository
from wq_workflow.offline.replay_repository import ReplayRepository


def test_replay_insufficient_generates_independent_estimate(tmp_path):
    db=tmp_path/'workflow.db'; seed_replay_decision(db)
    before=ReplayRepository(db_path=db).list_policy_decisions('run1')[0].to_dict()
    estimates=CounterfactualEvaluator(config=cfg(db), db_path=str(db)).evaluate_replay_run('run1')
    assert estimates and estimates[0].estimated_not_observed is True
    assert CounterfactualRepository(db_path=db).list_estimates()
    after=ReplayRepository(db_path=db).list_policy_decisions('run1')[0].to_dict()
    assert before==after
