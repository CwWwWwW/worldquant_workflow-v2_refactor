from types import SimpleNamespace

from wq_workflow.data.unit_of_work import IterationUnitOfWork


class Repo:
    def __init__(self, fail=False):
        self.rows = []
        self.fail = fail
    def upsert_candidate(self, row):
        if self.fail:
            raise RuntimeError("candidate fail")
        self.rows.append(row)
    def insert_iteration(self, row):
        if self.fail:
            raise RuntimeError("iteration fail")
        self.rows.append(row)
    def audit_prediction(self, *args, **kwargs):
        if self.fail:
            raise RuntimeError("audit fail")
        self.rows.append(args)


def _wf():
    return SimpleNamespace(iteration_id="i1", alpha_id="a1", candidate={"alpha_id": "a1"}, metrics={}, platform_sc={}, quality={}, reward=1.0, decisions=[], prediction_audits=[])


def test_uow_persist_result_main_success():
    candidate = Repo(); iteration = Repo()
    result = IterationUnitOfWork({"candidate": candidate, "iteration": iteration}).persist_result(_wf())
    assert result["fatal"] is False
    assert candidate.rows and iteration.rows


def test_uow_ml_audit_failure_not_fatal():
    wf = _wf(); wf.prediction_audits = [{"task_name": "x", "prediction_id": "p1"}]
    result = IterationUnitOfWork({"candidate": Repo(), "iteration": Repo(), "ml": Repo(fail=True)}).persist_result(wf)
    assert result["fatal"] is False


def test_uow_candidate_failure_is_fatal():
    result = IterationUnitOfWork({"candidate": Repo(fail=True), "iteration": Repo()}).persist_result(_wf())
    assert result["fatal"] is True
