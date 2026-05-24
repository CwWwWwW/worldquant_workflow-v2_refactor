from types import SimpleNamespace
from wq_workflow.learning.sc.policy import SCLearningPolicy
from wq_workflow.learning.parent.policy import ParentLearningPolicy
from wq_workflow.learning.policy.policy import ActionLearningPolicy
from wq_workflow.learning.outcome.policy import OutcomeSimulatorPolicy


class Gov:
    def __init__(self, allowed): self.allowed=allowed; self.calls=[]
    def allow_hard_decision(self, task, decision, cfg):
        self.calls.append((task,decision)); return type('D',(),{'allowed':self.allowed})()


class Pred:
    def predict(self,*a,**k): return {'learned_local_sc':0.1,'confidence':1.0}
    def rank_parents(self, parents, **k): return list(reversed(parents))
    def score_actions(self, actions, **k):
        out=[]
        for i,a in enumerate(actions):
            b=dict(a); b['action_score']=10-i; out.append(b)
        return out


def test_sc_parent_policy_simulator_governance_blocks_to_legacy():
    cfg=SimpleNamespace(enable_sc_model_fallback=True, sc_model_min_confidence=0.1, enable_parent_model_decision=True, enable_parent_model_prediction=True, enable_policy_model_decision=True, enable_policy_model_prediction=True, enable_simulator_model_skip=True, enable_simulator_model_prediction=False)
    gov=Gov(False)
    assert SCLearningPolicy(config=cfg,predictor=Pred(),governance_service=gov).decide(estimated_self_corr=0.4,features={})['final_sc_source'] == 'raw_local_proxy'
    assert ParentLearningPolicy(config=cfg,predictor=Pred(),governance_service=gov).select_parent([{'id':'a'},{'id':'b'}])['id'] == 'a'
    assert ActionLearningPolicy(config=cfg,predictor=Pred(),governance_service=gov).choose_action([{'id':'a'},{'id':'b'}], legacy_action={'id':'legacy'})['id'] == 'legacy'
    assert OutcomeSimulatorPolicy(config=cfg,governance_service=gov).evaluate_candidate({})['should_skip'] is False
