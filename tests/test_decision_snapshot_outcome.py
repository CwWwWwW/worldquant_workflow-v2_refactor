from wq_workflow.offline.repository import DecisionSnapshotRepository
from wq_workflow.offline.service import DecisionSnapshotService


def test_multiple_snapshots_alpha_outcome_and_missing_alpha(tmp_path):
    svc = DecisionSnapshotService(repository=DecisionSnapshotRepository(db_path=tmp_path / "workflow.db"))
    svc.startup_check()
    svc.record_decision("candidate_acceptance", {"decision_id": "d1", "alpha_id": "a1", "chosen_action": "submit"})
    svc.record_decision("experiment_arm_selection", {"decision_id": "d2", "alpha_id": "a1", "chosen_action": "arm"})
    outcomes = svc.record_outcome("a1", {"success": True, "reward": 1.5, "platform_sc_abs_max": 0.4, "quality_passed": True})
    assert len(outcomes) == 2
    assert all(item.platform_sc_abs_max == 0.4 for item in outcomes)
    assert svc.record_outcome(None, {"success": False}) == []
