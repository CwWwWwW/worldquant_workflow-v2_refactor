from wq_workflow.app.config_guard import apply_config_safety_gate
from wq_workflow.models import WorkflowConfig


class EmptyRegistry:
    def load_active_model(self, task):
        return None


def test_no_active_model_disables_hard_decision_flags():
    cfg = WorkflowConfig(
        enable_parent_model_decision=True,
        enable_policy_model_decision=True,
        enable_simulator_model_skip=True,
        enable_sc_model_fallback=True,
    )
    result = apply_config_safety_gate(cfg, model_registry=EmptyRegistry())
    effective = result["effective_config"]
    assert effective.enable_parent_model_decision is False
    assert effective.enable_policy_model_decision is False
    assert effective.enable_simulator_model_skip is False
    assert effective.enable_sc_model_fallback is False


def test_refactored_pipeline_disabled_when_unsafe():
    cfg = WorkflowConfig(enable_refactored_pipeline=True, allow_observe_only_pipeline=False)
    result = apply_config_safety_gate(cfg, model_registry=EmptyRegistry())
    assert result["effective_config"].enable_refactored_pipeline is False


def test_config_guard_does_not_modify_original_config():
    cfg = WorkflowConfig(enable_parent_model_decision=True)
    result = apply_config_safety_gate(cfg, model_registry=EmptyRegistry())
    assert cfg.enable_parent_model_decision is True
    assert result["effective_config"].enable_parent_model_decision is False


def test_force_enable_unsafe_ml_decisions_keeps_flags_with_warning():
    cfg = WorkflowConfig(enable_parent_model_decision=True, force_enable_unsafe_ml_decisions=True)
    result = apply_config_safety_gate(cfg, model_registry=EmptyRegistry())
    assert result["effective_config"].enable_parent_model_decision is True
    assert any("UNSAFE" in warning for warning in result["warnings"])
