from types import SimpleNamespace

from wq_workflow.data.repositories import RepositoryBundle
from wq_workflow.offline.support_checker import SupportChecker


def _cfg(**overrides):
    base = {"support_min_action_count": 2, "support_min_context_count": 2, "offline_replay_max_decisions": 100}
    base.update(overrides)
    return SimpleNamespace(**base)


def test_action_support_sufficient_and_coverage(tmp_path):
    repos = RepositoryBundle.from_storage(db_path=tmp_path / "workflow.db")
    for i in range(2):
        repos.decision.insert_decision_snapshot(
            decision_id=f"d{i}",
            decision_type="policy_action",
            context={"mutation_type": "m1"},
            chosen_action={"action_id": "mutate", "action_type": "m1"},
        )
    checker = SupportChecker(repos, _cfg(), None)
    result = checker.check_action_support("policy_action", "mutate", {"mutation_type": "m1"})
    assert result["support_pass"] is True
    assert result["support_coverage"] == 1.0


def test_action_support_insufficient(tmp_path):
    repos = RepositoryBundle.from_storage(db_path=tmp_path / "workflow.db")
    repos.decision.insert_decision_snapshot(decision_id="d1", decision_type="policy_action", chosen_action={"action_id": "mutate"})
    result = SupportChecker(repos, _cfg(), None).check_action_support("policy_action", "mutate")
    assert result["support_pass"] is False
    assert "action_count_below_minimum" in result["warnings"]


def test_parent_and_strategy_support_insufficient(tmp_path):
    repos = RepositoryBundle.from_storage(db_path=tmp_path / "workflow.db")
    checker = SupportChecker(repos, _cfg(), None)
    assert checker.check_parent_support({"family": "f1"})["support_pass"] is False
    assert checker.check_strategy_support("parent_learning_challenger")["support_pass"] is False
