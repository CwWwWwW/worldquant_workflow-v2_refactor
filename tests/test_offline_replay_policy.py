from wq_workflow.offline.replay_policy import (
    ActualChosenReplayPolicy,
    BudgetChoiceReplayPolicy,
    ExperimentChoiceReplayPolicy,
    LegacyReplayPolicy,
    ModelChoiceReplayPolicy,
)
from wq_workflow.offline.schema import DecisionAction, ReplayRecord


def test_replay_policies_return_expected_choices():
    actual = DecisionAction(action_id="actual")
    legacy = DecisionAction(action_id="legacy")
    model = DecisionAction(action_id="model")
    experiment = DecisionAction(action_id="experiment")
    budget = DecisionAction(action_id="budget", source="budget")
    record = ReplayRecord(chosen_action=actual, legacy_choice=legacy, model_choice=model, experiment_choice=experiment, budget_choice=budget)
    assert ActualChosenReplayPolicy().choose_action(record).action_id == "actual"
    assert LegacyReplayPolicy().choose_action(record).action_id == "legacy"
    assert ModelChoiceReplayPolicy().choose_action(record).action_id == "model"
    assert ExperimentChoiceReplayPolicy().choose_action(record).action_id == "experiment"
    assert BudgetChoiceReplayPolicy().choose_action(record).action_id == "budget"


def test_replay_policies_missing_fields_are_safe():
    record = ReplayRecord(chosen_action=DecisionAction(action_id="actual"), budget_plan_id="bp1")
    legacy = LegacyReplayPolicy()
    assert legacy.choose_action(record).action_id == "actual"
    assert "missing_legacy_choice" in legacy.last_reason_codes
    model = ModelChoiceReplayPolicy()
    assert model.choose_action(record) is None
    assert "missing_model_choice" in model.last_reason_codes
    assert BudgetChoiceReplayPolicy().choose_action(record).action_id == "bp1"
