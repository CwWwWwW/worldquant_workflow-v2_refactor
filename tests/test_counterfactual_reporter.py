from wq_workflow.offline.counterfactual_reporter import CounterfactualReporter
from wq_workflow.offline.counterfactual_repository import CounterfactualRepository
from wq_workflow.offline.schema import CounterfactualEstimate, CounterfactualRequest


def test_reporter_atomic_corrupt_rebuild(tmp_path):
    db=tmp_path/'workflow.db'; path=tmp_path/'counterfactual_report.json'
    repo=CounterfactualRepository(db_path=db); repo.initialize()
    repo.save_request(CounterfactualRequest(request_id='r', decision_id='d', decision_type='t'))
    repo.save_estimate(CounterfactualEstimate(estimate_id='e', request_id='r', decision_id='d'))
    repo.update_summary('t')
    path.write_text('{bad', encoding='utf-8')
    result=CounterfactualReporter(repository=repo,status_path=path).update(enabled=False)
    assert result['ok'] and path.exists()
    assert list(tmp_path.glob('counterfactual_report.json.corrupt.*.bak'))
    assert result['summaries'] and result['recent_estimates']
