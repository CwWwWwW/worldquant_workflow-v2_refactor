from wq_workflow.offline.replay_dataset import ReplayDatasetLoader
from wq_workflow.offline.replay_policy import BudgetChoiceReplayPolicy
from wq_workflow.offline.repository import DecisionSnapshotRepository
from wq_workflow.offline.schema import DecisionAction, DecisionOutcome, DecisionSnapshot, ReplayDatasetFilter


def test_phase5a_snapshots_feed_phase5b_replay_dataset(tmp_path):
    db_path = tmp_path / "workflow.db"
    repo = DecisionSnapshotRepository(db_path=db_path)
    budget = DecisionAction(action_id="bp1", source="budget", metadata={"budget_plan_id": "bp1"})
    repo.save_snapshot(
        DecisionSnapshot(
            decision_id="d1",
            decision_type="budget_plan_selection",
            alpha_id="alpha1",
            experiment_id="exp1",
            arm_id="arm1",
            budget_plan_id="bp1",
            available_actions=[budget],
            chosen_action=budget,
            legacy_choice=budget,
            context={"budget_choice": budget.to_dict()},
        )
    )
    repo.save_outcome(DecisionOutcome(outcome_id="o1", decision_id="d1", alpha_id="alpha1", reward=0.5, success=True))
    record = ReplayDatasetLoader(db_path=db_path).load_records(ReplayDatasetFilter(require_outcome=True))[0]
    assert record.alpha_id == "alpha1"
    assert record.experiment_id == "exp1"
    assert record.arm_id == "arm1"
    assert record.budget_plan_id == "bp1"
    assert BudgetChoiceReplayPolicy().choose_action(record).action_id == "bp1"
    assert repo.count_snapshots() == 1
