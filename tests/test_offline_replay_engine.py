from wq_workflow.offline.replay_engine import ReplayEngine
from wq_workflow.offline.repository import DecisionSnapshotRepository
from wq_workflow.offline.schema import DecisionAction, DecisionOutcome, DecisionSnapshot, ReplayDatasetFilter, ReplayRecord


def test_replay_engine_empty_dataset_insufficient(tmp_path):
    engine = ReplayEngine(db_path=str(tmp_path / "workflow.db"))
    run = engine.run_replay(ReplayDatasetFilter())
    assert run.status == "insufficient_data"
    assert run.sample_count == 0


def test_replay_engine_observable_and_unobserved_actions(tmp_path):
    actual = DecisionAction(action_id="a1")
    model = DecisionAction(action_id="a2")
    record = ReplayRecord(decision_id="d1", chosen_action=actual, legacy_choice=actual, model_choice=model, outcome=DecisionOutcome(decision_id="d1", reward=2.0, success=True), reward=2.0, success=True)
    engine = ReplayEngine(db_path=str(tmp_path / "workflow.db"))
    legacy_decision = engine.evaluate_policy_decision(record, engine._normalize_policies(["legacy"])[0], "r1")
    model_decision = engine.evaluate_policy_decision(record, engine._normalize_policies(["model_choice"])[0], "r1")
    assert legacy_decision.observable_outcome is True
    assert legacy_decision.reward == 2.0
    assert model_decision.observable_outcome is False
    assert model_decision.reward is None
    assert "insufficient_counterfactual_evidence" in model_decision.reason_codes


def test_replay_engine_full_run_generates_outputs(tmp_path):
    db_path = tmp_path / "workflow.db"
    repo = DecisionSnapshotRepository(db_path=db_path)
    action = DecisionAction(action_id="a1")
    repo.save_snapshot(DecisionSnapshot(decision_id="d1", decision_type="experiment_arm_selection", chosen_action=action, legacy_choice=action, model_choice=DecisionAction(action_id="a2")))
    repo.save_outcome(DecisionOutcome(outcome_id="o1", decision_id="d1", reward=1.0, success=True))
    engine = ReplayEngine(db_path=str(db_path))
    run = engine.run_replay(ReplayDatasetFilter())
    assert run.status == "completed"
    decisions = engine.repository.list_policy_decisions(run.replay_run_id)
    assert decisions
    assert engine.repository.list_policy_metrics(run.replay_run_id)
    assert engine.repository.list_comparisons(run.replay_run_id)
