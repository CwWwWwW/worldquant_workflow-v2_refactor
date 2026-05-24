from wq_workflow.governance.lifecycle import ModelLifecycleMetadata, ModelLifecycleStatus, can_transition, default_weight_for_status, is_hard_decision_allowed_status


def test_lifecycle_rules():
    assert {s.value for s in ModelLifecycleStatus} >= {'candidate','shadow','challenger','limited_active','champion','degraded','disabled','rolled_back','expired'}
    assert not can_transition('candidate','champion')
    assert default_weight_for_status('disabled') == 0.0
    assert default_weight_for_status('expired') == 0.0
    assert not is_hard_decision_allowed_status('shadow')
    assert is_hard_decision_allowed_status('limited_active')
    meta = ModelLifecycleMetadata(lifecycle_status='disabled', model_weight=1.0)
    assert ModelLifecycleMetadata.from_dict(meta.to_dict()).model_weight == 0.0
