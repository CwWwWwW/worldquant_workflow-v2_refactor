from wq_workflow.workflow.context import WorkflowContext
from wq_workflow.workflow.steps import LearningSampleStep, PersistResultStep


class UOW:
    def __init__(self):
        self.called = False
    def persist_result(self, wf):
        self.called = True
        return {"ok": True, "fatal": False, "written": ["candidate", "iteration"], "errors": []}


class Store:
    def __init__(self, fail=False):
        self.called = False
        self.fail = fail
    def record_if_complete(self, **kwargs):
        self.called = True
        if self.fail:
            raise RuntimeError("boom")
        return "sc1"
    def record_parent_outcome(self, *args):
        self.called = True
        return "p1"
    def record_policy_outcome(self, *args):
        self.called = True
        return "pol1"
    def record_simulator_outcome(self, *args):
        self.called = True
        return "s1"


class Ctx:
    def __init__(self):
        self.logger = None
        self.data_services = {"unit_of_work": UOW()}
        self.learning_services = {}


def test_persist_result_step_calls_uow():
    ctx = Ctx()
    result = PersistResultStep(ctx).run(WorkflowContext(iteration_id="i1"))
    assert result.data["persisted"] is True
    assert ctx.data_services["unit_of_work"].called is True


def test_learning_sample_step_isolates_store_errors():
    ctx = Ctx()
    bad = Store(fail=True); parent = Store(); policy = Store(); outcome = Store()
    ctx.learning_services = {"sc_sample_store": bad, "parent_sample_store": parent, "policy_sample_store": policy, "outcome_sample_store": outcome}
    wf = WorkflowContext(iteration_id="i1", alpha_id="a1", candidate={"alpha_id": "a1"})
    result = LearningSampleStep(ctx).run(wf)
    assert result.ok is True
    assert "error" in result.data["learning_samples"]["sc"]
    assert parent.called and policy.called and outcome.called
