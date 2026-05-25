from tests.counterfactual_test_helpers import cfg, seed_replay_decision
from wq_workflow.offline.service import CounterfactualService


def test_governance_can_read_summary_without_hard_flags(tmp_path):
    db=tmp_path/'workflow.db'; seed_replay_decision(db)
    service=CounterfactualService(config=cfg(db), db_path=db); service.startup_check(); service.evaluate_replay_run('run1')
    summary=service.get_counterfactual_evidence_summary()
    assert summary['available'] is True
    assert 'hard_decision' not in str(summary).lower()
    assert 'promotion' not in str(summary).lower()
    assert 'rollback' not in str(summary).lower()
