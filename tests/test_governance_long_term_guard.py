from wq_workflow.governance.long_term_guard import LongTermGuard
from wq_workflow.governance.schema import GovernanceCheckResult


class Adapter:
    def __init__(self): self.weight=False; self.disabled=False
    def get_active_metadata(self,t): return {'model_version':'v1','raw_payload':{'lifecycle_status':'champion'}}
    def check_registry_consistency(self,t=None): return {'ok':True,'issues':[]}
    def update_model_weight(self,*a): self.weight=True; return True
    def disable_active_model(self,*a,**k): self.disabled=True; return True


class Eval:
    def __init__(self, action): self.action=action
    def evaluate_task(self,t,v):
        return type('R',(),{'recommended_action':self.action,'to_dict':lambda s:{'recommended_action':self.action}})()


def test_no_active_force_legacy():
    g=LongTermGuard(registry_adapter=type('A',(),{'get_active_metadata':lambda s,t:None})())
    assert g.check_task('sc').recommended_action == 'force_legacy'


def test_reduce_and_disable_actions():
    a=Adapter(); g=LongTermGuard(registry_adapter=a, online_evaluator=Eval('reduce_weight'), config=type('C',(),{'enable_online_model_evaluation':True})())
    assert g.check_task('sc').recommended_action == 'reduce_weight' and a.weight
    a=Adapter(); g=LongTermGuard(registry_adapter=a, online_evaluator=Eval('disable_model'), config=type('C',(),{'enable_online_model_evaluation':True})())
    assert g.check_task('sc').recommended_action == 'disable_model' and a.disabled
