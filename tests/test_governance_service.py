from types import SimpleNamespace
from wq_workflow.governance.service import LearningGovernanceService


def test_service_init_and_unavailable_gate(tmp_path):
    cfg=SimpleNamespace(storage_db_path=str(tmp_path/'db.sqlite'), governance_status_path=str(tmp_path/'g.json'), ml_status_path=str(tmp_path/'m.json'), enable_online_model_evaluation=False, enable_sc_model_fallback=True, force_enable_unsafe_ml_decisions=False)
    s=LearningGovernanceService(config=cfg, db_path=tmp_path/'db.sqlite', model_root=tmp_path/'models', root=tmp_path)
    assert s.available
    assert not s.allow_hard_decision('sc','sc_fallback',cfg).allowed
    assert s.handle_prediction_error('sc','bad').recommended_action == 'force_legacy'
