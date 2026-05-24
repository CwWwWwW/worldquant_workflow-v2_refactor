from wq_workflow.governance.schema import GovernanceAction, GovernanceCheckResult, GovernanceDecision, TaskGovernanceState


def test_schema_roundtrips():
    objs = [
        GovernanceDecision(True,'ok','sc','sc_fallback','v1','champion',1.0,False,['w'],{'x':1}),
        GovernanceAction('disable_model','sc','v1','bad',{'x':1}),
        GovernanceCheckResult(False,'sc','force_legacy','bad',['w'],{'x':1}),
        TaskGovernanceState('sc','v1','shadow',0.0,True,{'a':1},{'e':1},'now'),
    ]
    for obj in objs:
        assert type(obj).from_dict(obj.to_dict()).to_dict() == obj.to_dict()
