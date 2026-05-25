from tests.counterfactual_test_helpers import seed_observed, seed_replay_decision, cfg
from wq_workflow.offline.counterfactual_dataset import CounterfactualDatasetLoader


def test_dataset_only_observed_and_replay_request(tmp_path):
    db=tmp_path/'workflow.db'; seed_observed(db); pd=seed_replay_decision(db)
    loader=CounterfactualDatasetLoader(db_path=db, config=cfg(db))
    records=loader.load_observed_records('experiment_arm_selection')
    assert records and all(r.outcome is not None for r in records)
    assert 'no_outcome' not in {r.decision_id for r in records}
    decisions=loader.load_replay_policy_decisions('run1')
    req=loader.build_request_from_policy_decision(decisions[0], loader.load_record_for_decision(pd.decision_id))
    assert req and req.policy_decision_id=='pd1'
    assert CounterfactualDatasetLoader(db_path=tmp_path/'empty.db').load_observed_records()==[]
