from wq_workflow.offline.counterfactual_repository import CounterfactualRepository
from wq_workflow.offline.schema import CounterfactualEvidence, CounterfactualEstimate, CounterfactualRequest


def test_repository_idempotent_crud_and_summary(tmp_path):
    repo=CounterfactualRepository(db_path=tmp_path/'workflow.db'); assert repo.initialize()['ok']
    req=CounterfactualRequest(request_id='r', decision_id='d', decision_type='t')
    repo.save_request(req); repo.save_request(req)
    assert repo.get_request('r').decision_id=='d'
    ev=CounterfactualEvidence(evidence_id='e', request_id='r', source_decision_id='s', similarity_score=0.8)
    repo.save_evidence(ev); repo.save_evidence(ev)
    assert len(repo.list_evidence('r'))==1
    est=CounterfactualEstimate(estimate_id='est', request_id='r', decision_id='d', evidence_count=1)
    repo.save_estimate(est); repo.save_estimate(est)
    assert repo.get_estimate('est').decision_id=='d'
    assert len(repo.list_estimates(decision_type='t'))==1
    assert repo.update_summary('t').request_count==1
    assert repo.list_summaries()
