import sqlite3

from wq_workflow.offline.decision_snapshot import DecisionSnapshotBuilder
from wq_workflow.offline.repository import DecisionSnapshotRepository
from wq_workflow.offline.schema import DecisionOutcome


def test_repository_snapshot_outcome_summary_idempotent(tmp_path):
    conn = sqlite3.connect(tmp_path / "workflow.db")
    conn.row_factory = sqlite3.Row
    repo = DecisionSnapshotRepository(conn=conn)
    assert repo.initialize()["ok"] is True
    builder = DecisionSnapshotBuilder()
    snap = builder.build_snapshot("candidate_acceptance", {"alpha_id": "a1", "chosen_action": {"id": "submit"}, "available_actions": ["submit"]})
    assert repo.save_snapshot(snap)["ok"] is True
    assert repo.save_snapshot(snap)["ok"] is True
    assert repo.get_snapshot(snap.decision_id).alpha_id == "a1"
    assert len(repo.list_snapshots(decision_type="candidate_acceptance")) == 1
    assert len(repo.find_snapshots_by_alpha("a1")) == 1

    outcome = DecisionOutcome(outcome_id="o1", decision_id=snap.decision_id, alpha_id="a1", success=True, reward=2.0, platform_sc_abs_max=0.2)
    assert repo.save_outcome(outcome)["ok"] is True
    assert repo.get_outcomes_for_decision(snap.decision_id)[0].reward == 2.0
    repo.update_snapshot_outcome(snap.decision_id, outcome.to_dict())
    repo.update_summary("candidate_acceptance")
    summaries = repo.list_summaries()
    assert summaries[0].sample_count == 1
    assert summaries[0].outcome_count == 1
    assert summaries[0].avg_reward == 2.0
