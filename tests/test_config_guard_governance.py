from wq_workflow.app.config_guard import apply_config_safety_gate
from wq_workflow.models import WorkflowConfig


class Gov:
    def allow_hard_decision(self,*a,**k):
        return type('D',(),{'allowed':False,'reason':'blocked','warnings':[]})()


def test_config_guard_uses_governance_gate():
    cfg=WorkflowConfig(enable_sc_model_fallback=True, enable_simulator_model_skip=True)
    r=apply_config_safety_gate(cfg, governance_service=Gov())
    assert not r['effective_config'].enable_sc_model_fallback
    assert not r['effective_config'].enable_simulator_model_skip


def test_force_unsafe_keeps_flag():
    cfg=WorkflowConfig(enable_sc_model_fallback=True, force_enable_unsafe_ml_decisions=True)
    r=apply_config_safety_gate(cfg, governance_service=Gov())
    assert r['effective_config'].enable_sc_model_fallback
    assert r['warnings']
