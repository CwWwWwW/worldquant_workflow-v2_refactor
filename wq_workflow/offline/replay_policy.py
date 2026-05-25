from __future__ import annotations

from typing import Any

from .schema import DecisionAction, ReplayRecord


def action_key(action: Any) -> str:
    if action is None:
        return ""
    item = DecisionAction.from_dict(action)
    return str(item.action_id or item.name or item.metadata.get("alpha_id") or item.metadata.get("id") or "").strip()


def actions_match(left: Any, right: Any) -> bool:
    if left is None or right is None:
        return False
    left_item = DecisionAction.from_dict(left)
    right_item = DecisionAction.from_dict(right)
    left_key = action_key(left_item)
    right_key = action_key(right_item)
    if left_key or right_key:
        return left_key == right_key
    return left_item.to_dict() == right_item.to_dict()


class ReplayPolicy:
    def __init__(self) -> None:
        self.last_reason_codes: list[str] = []

    def name(self) -> str:
        raise NotImplementedError

    def choose_action(self, record: ReplayRecord) -> DecisionAction | None:
        raise NotImplementedError

    def _reset(self) -> None:
        self.last_reason_codes = []


class ActualChosenReplayPolicy(ReplayPolicy):
    def name(self) -> str:
        return "actual_chosen"

    def choose_action(self, record: ReplayRecord) -> DecisionAction | None:
        self._reset()
        if record.chosen_action is None:
            self.last_reason_codes.append("missing_chosen_action")
        return record.chosen_action


class LegacyReplayPolicy(ReplayPolicy):
    def name(self) -> str:
        return "legacy"

    def choose_action(self, record: ReplayRecord) -> DecisionAction | None:
        self._reset()
        if record.legacy_choice is not None:
            return record.legacy_choice
        self.last_reason_codes.append("missing_legacy_choice")
        return record.chosen_action


class ModelChoiceReplayPolicy(ReplayPolicy):
    def name(self) -> str:
        return "model_choice"

    def choose_action(self, record: ReplayRecord) -> DecisionAction | None:
        self._reset()
        if record.model_choice is None:
            self.last_reason_codes.append("missing_model_choice")
        return record.model_choice


class ExperimentChoiceReplayPolicy(ReplayPolicy):
    def name(self) -> str:
        return "experiment_choice"

    def choose_action(self, record: ReplayRecord) -> DecisionAction | None:
        self._reset()
        if record.experiment_choice is None:
            self.last_reason_codes.append("missing_experiment_choice")
        return record.experiment_choice


class BudgetChoiceReplayPolicy(ReplayPolicy):
    def name(self) -> str:
        return "budget_choice"

    def choose_action(self, record: ReplayRecord) -> DecisionAction | None:
        self._reset()
        if record.budget_choice is not None:
            return record.budget_choice
        candidate = _find_budget_choice(record)
        if candidate is None:
            self.last_reason_codes.append("missing_budget_choice")
        return candidate


def default_replay_policies(names: list[str] | None = None) -> list[ReplayPolicy]:
    factories = {
        "actual_chosen": ActualChosenReplayPolicy,
        "legacy": LegacyReplayPolicy,
        "model_choice": ModelChoiceReplayPolicy,
        "experiment_choice": ExperimentChoiceReplayPolicy,
        "budget_choice": BudgetChoiceReplayPolicy,
    }
    selected = names or ["actual_chosen", "legacy", "model_choice", "experiment_choice", "budget_choice"]
    policies: list[ReplayPolicy] = []
    for name in selected:
        factory = factories.get(str(name))
        if factory is not None:
            policies.append(factory())
    return policies


def _find_budget_choice(record: ReplayRecord) -> DecisionAction | None:
    data_sources: list[Any] = [
        record.context.get("budget_choice"),
        record.context.get("budget_action"),
        record.context.get("budget_recommendation"),
        record.raw_payload.get("budget_choice"),
        record.raw_payload.get("budget_action"),
        record.raw_payload.get("budget_recommendation"),
    ]
    for value in data_sources:
        if value:
            return DecisionAction.from_dict(value)
    plan_id = record.budget_plan_id or record.context.get("budget_plan_id") or record.raw_payload.get("budget_plan_id")
    if plan_id:
        for action in record.available_actions:
            item = DecisionAction.from_dict(action)
            if item.action_id == str(plan_id) or item.metadata.get("budget_plan_id") == plan_id:
                return item
        return DecisionAction(action_id=str(plan_id), action_type="budget_plan_selection", name=str(plan_id), source="budget", metadata={"budget_plan_id": str(plan_id)})
    return None
