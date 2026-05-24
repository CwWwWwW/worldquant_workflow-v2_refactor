from types import SimpleNamespace

from wq_workflow.offline.repository import DecisionSnapshotRepository
from wq_workflow.offline.service import DecisionSnapshotService


def test_service_startup_record_outcome_report(tmp_path):
    cfg = SimpleNamespace(enable_decision_snapshots=True, decision_snapshot_status_path=str(tmp_path / "status.json"), decision_snapshot_fail_open=True)
    svc = DecisionSnapshotService(config=cfg, repository=DecisionSnapshotRepository(db_path=tmp_path / "workflow.db"))
    assert svc.startup_check()["ok"] is True
    snap = svc.record_decision("candidate_acceptance", {"alpha_id": "a1", "chosen_action": "submit", "available_actions": ["submit"]})
    assert snap is not None
    outcomes = svc.record_outcome("a1", {"success": True, "reward": 1.0, "quality_passed": True})
    assert len(outcomes) == 1
    assert svc.update_report()["ok"] is True
    assert (tmp_path / "status.json").exists()


def test_service_failure_no_fatal():
    class BadRepo:
        last_error = "bad"
        def initialize(self):
            return {"ok": False, "error": "bad"}
    svc = DecisionSnapshotService(repository=BadRepo(), config=SimpleNamespace(enable_decision_snapshots=True, decision_snapshot_fail_open=True))
    assert svc.startup_check()["ok"] is False
    assert svc.record_decision("candidate_acceptance", {}) is None
    assert svc.record_outcome(None, {}) == []
