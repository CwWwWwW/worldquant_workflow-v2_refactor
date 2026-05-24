from types import SimpleNamespace
from wq_workflow.governance.retrain_scheduler import RetrainScheduler


def test_should_retrain_triggers():
    s = RetrainScheduler(config=SimpleNamespace(enable_auto_retrain=True, ml_min_retrain_interval_minutes=0, ml_retrain_every_samples=50))
    assert s.should_retrain('sc', metadata=None).recommended_action == 'retrain'
    assert s.should_retrain('sc', metadata={'raw_payload':{}}, sample_count=50).recommended_action == 'retrain'


def test_trainer_exception_nonfatal():
    def bad(): raise RuntimeError('boom')
    s = RetrainScheduler(config=SimpleNamespace(enable_auto_retrain=True, ml_auto_disable_on_retrain_failure=True), trainers={'sc': bad})
    r = s.run_retrain('sc')
    assert not r.ok and r.recommended_action == 'force_legacy'
