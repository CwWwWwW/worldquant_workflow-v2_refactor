from tests.counterfactual_test_helpers import cfg, seed_replay_decision
from wq_workflow.offline.service import CounterfactualService


def test_service_disabled_startup_manual_run_and_report(tmp_path):
    db=tmp_path/'workflow.db'; seed_replay_decision(db)
    service=CounterfactualService(config=cfg(db), db_path=db)
    status=service.startup_check()
    assert status['ok'] and status['enabled'] is False and status['auto_run'] is False
    assert service.evaluate_replay_run('run1')
    assert isinstance(service.get_latest_report(), dict)
    assert service.get_counterfactual_evidence_summary()['available'] is True
