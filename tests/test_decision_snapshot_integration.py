from types import SimpleNamespace

from wq_workflow.offline.repository import DecisionSnapshotRepository
from wq_workflow.offline.service import DecisionSnapshotService


def test_candidate_acceptance_integration(tmp_path):
    svc = DecisionSnapshotService(config=SimpleNamespace(enable_decision_snapshots=True, decision_snapshot_status_path=str(tmp_path / "status.json")), repository=DecisionSnapshotRepository(db_path=tmp_path / "workflow.db"))
    svc.startup_check()
    snap = svc.record_decision("candidate_acceptance", {"alpha_id": "a1", "template_name": "t", "chosen_action": {"id": "submit"}, "available_actions": ["submit", "skip"]})
    assert snap is not None
    assert svc.record_outcome("a1", {"success": True, "reward": 0.7})
    status = svc.update_report()
    assert status["snapshot_count"] == 1
