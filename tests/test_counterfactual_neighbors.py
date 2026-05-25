from tests.counterfactual_test_helpers import seed_observed
from wq_workflow.offline.counterfactual_dataset import CounterfactualDatasetLoader
from wq_workflow.offline.counterfactual_neighbors import CounterfactualNeighborIndex
from wq_workflow.offline.schema import CounterfactualRequest


def test_neighbors_threshold_sorted_observed(tmp_path):
    db=tmp_path/'workflow.db'; action=seed_observed(db)
    records=CounterfactualDatasetLoader(db_path=db).load_observed_records()
    req=CounterfactualRequest(request_id='r', decision_id='d', decision_type='experiment_arm_selection', target_action=action, features={'operator_family':'op'}, context={'behavior_family':'beh'}, min_evidence=2)
    ev=CounterfactualNeighborIndex().find_neighbors(req, records, threshold=0.1)
    assert ev and all(e.similarity_score>=0.1 for e in ev)
    assert [e.similarity_score for e in ev] == sorted([e.similarity_score for e in ev], reverse=True)
    assert CounterfactualNeighborIndex().find_neighbors(req, records, threshold=0.99)==[]
