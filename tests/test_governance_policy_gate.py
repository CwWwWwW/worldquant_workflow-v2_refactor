from types import SimpleNamespace
from wq_workflow.governance.policy_gate import GovernancePolicyGate


class Adapter:
    def __init__(self, status='shadow', raw=None): self.status=status; self.raw=raw or {}
    def get_active_metadata(self,t): return {'model_version':'v1','lifecycle_status':self.status,'model_weight':1.0,'raw_payload':{'lifecycle_status':self.status,'model_weight':1.0, **self.raw}}
    def check_registry_consistency(self,t=None): return {'ok':True,'issues':[]}


def test_shadow_blocks_and_champion_allows():
    cfg=SimpleNamespace(enable_sc_model_fallback=True, force_enable_unsafe_ml_decisions=False)
    assert not GovernancePolicyGate(Adapter('shadow'), cfg).allow_hard_decision('sc','sc_fallback',cfg).allowed
    assert GovernancePolicyGate(Adapter('champion'), cfg).allow_hard_decision('sc','sc_fallback',cfg).allowed


def test_simulator_unknown_risk_blocks_and_force_warns():
    cfg=SimpleNamespace(enable_simulator_model_skip=True, force_enable_unsafe_ml_decisions=False, simulator_max_false_skip_rate=0.02, simulator_validation_backtest_budget=0.1)
    assert not GovernancePolicyGate(Adapter('champion'), cfg).allow_hard_decision('simulator','simulator_skip',cfg).allowed
    cfg.force_enable_unsafe_ml_decisions=True
    d=GovernancePolicyGate(Adapter('shadow'), cfg).allow_hard_decision('simulator','simulator_skip',cfg)
    assert d.allowed and d.warnings
