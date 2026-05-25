import json

from wq_workflow.offline.schema import (
    DecisionAction,
    DecisionOutcome,
    ReplayComparison,
    ReplayDatasetFilter,
    ReplayPolicyDecision,
    ReplayPolicyMetrics,
    ReplayRecord,
    ReplayRun,
)


def test_offline_replay_schema_roundtrip_json_safe():
    action = DecisionAction(action_id="a1", source="legacy")
    outcome = DecisionOutcome(decision_id="d1", reward=1.2, success=True)
    objects = [
        ReplayDatasetFilter(decision_types=["experiment_arm_selection"], require_outcome=True, raw_payload={"x": 1}),
        ReplayRecord(decision_id="d1", available_actions=[action], chosen_action=action, outcome=outcome, reward=1.2),
        ReplayPolicyDecision(replay_run_id="r1", decision_id="d1", policy_name="legacy", selected_action=action, observable_outcome=True, reward=1.2),
        ReplayRun(replay_run_id="r1", policies=["legacy"], sample_count=1),
        ReplayPolicyMetrics(replay_run_id="r1", policy_name="legacy", sample_count=1, observable_count=1, coverage_rate=1.0),
        ReplayComparison(replay_run_id="r1", baseline_policy="legacy", challenger_policy="model_choice"),
    ]
    for obj in objects:
        data = obj.to_dict()
        json.dumps(data)
        restored = obj.__class__.from_dict(data)
        assert restored.to_dict() == data


def test_replay_schema_uses_timezone_iso_defaults():
    run = ReplayRun()
    assert "T" in run.started_at
    assert "+" in run.started_at
