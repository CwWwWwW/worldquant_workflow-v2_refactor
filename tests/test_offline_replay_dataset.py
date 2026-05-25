from wq_workflow.offline.replay_dataset import ReplayDatasetLoader
from wq_workflow.offline.repository import DecisionSnapshotRepository
from wq_workflow.offline.schema import DecisionAction, DecisionOutcome, DecisionSnapshot, ReplayDatasetFilter


def _seed(db_path):
    repo = DecisionSnapshotRepository(db_path=db_path)
    action = DecisionAction(action_id="a1", source="legacy")
    repo.save_snapshot(
        DecisionSnapshot(
            decision_id="d1",
            decision_type="experiment_arm_selection",
            alpha_id="alpha1",
            experiment_id="exp1",
            arm_id="arm1",
            budget_plan_id="bp1",
            available_actions=[action],
            chosen_action=action,
            legacy_choice=action,
        )
    )
    repo.save_outcome(DecisionOutcome(outcome_id="o1", decision_id="d1", alpha_id="alpha1", reward=1.0, success=True))
    repo.save_snapshot(DecisionSnapshot(decision_id="d2", decision_type="budget_plan_selection", chosen_action=DecisionAction(action_id="bp2")))


def test_replay_dataset_loads_snapshots_and_outcomes(tmp_path):
    db_path = tmp_path / "workflow.db"
    _seed(db_path)
    records = ReplayDatasetLoader(db_path=db_path).load_records(ReplayDatasetFilter())
    assert {r.decision_id for r in records} == {"d1", "d2"}
    assert next(r for r in records if r.decision_id == "d1").outcome is not None


def test_replay_dataset_filters_require_outcome_and_context_ids(tmp_path):
    db_path = tmp_path / "workflow.db"
    _seed(db_path)
    loader = ReplayDatasetLoader(db_path=db_path)
    records = loader.load_records(ReplayDatasetFilter(require_outcome=True, decision_types=["experiment_arm_selection"], experiment_id="exp1", arm_id="arm1", budget_plan_id="bp1"))
    assert len(records) == 1
    assert records[0].alpha_id == "alpha1"
    assert records[0].budget_plan_id == "bp1"
