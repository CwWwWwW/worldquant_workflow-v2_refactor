import json
from datetime import UTC, datetime

from wq_workflow.offline.schema import DecisionAction, DecisionOutcome, DecisionSnapshot, DecisionSnapshotSummary


def test_decision_snapshot_schema_roundtrip_json_safe():
    action = DecisionAction(action_id="a1", action_type="parent", name="p1", source="legacy", score=1.0, rank=1, metadata={"x": object()})
    data = action.to_dict()
    json.dumps(data)
    assert DecisionAction.from_dict(data).action_id == "a1"

    snapshot = DecisionSnapshot(decision_id="d1", decision_type="candidate_acceptance", alpha_id="alpha", available_actions=[action], chosen_action=action, features={"bad": object()})
    snap_data = snapshot.to_dict()
    json.dumps(snap_data)
    restored = DecisionSnapshot.from_dict(snap_data)
    assert restored.available_actions[0].source == "legacy"
    assert restored.created_at.endswith("+00:00")
    datetime.fromisoformat(restored.created_at).tzinfo is not None

    outcome = DecisionOutcome(outcome_id="o1", decision_id="d1", alpha_id="alpha", success=True, reward=0.5)
    assert DecisionOutcome.from_dict(outcome.to_dict()).success is True

    summary = DecisionSnapshotSummary(decision_type="candidate_acceptance", sample_count=1, outcome_count=1, success_count=1)
    assert DecisionSnapshotSummary.from_dict(summary.to_dict()).sample_count == 1
