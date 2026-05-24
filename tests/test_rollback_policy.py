from types import SimpleNamespace

from wq_workflow.data.repositories import RepositoryBundle
from wq_workflow.strategy.rollback import RollbackPolicy


class Tracker:
    def __init__(self, reward=-0.2, risk=0.0, failure=0.0):
        self.reward = reward
        self.risk = risk
        self.failure = failure

    def compare_champion_vs_challenger(self, champion_id, challenger_id):
        return {"reward_delta": self.reward, "sc_risk_delta": self.risk, "failure_rate_delta": self.failure}


def _cfg():
    return SimpleNamespace(rollback_reward_drop_threshold=0.1, rollback_sc_risk_increase_threshold=0.05, rollback_failure_rate_increase_threshold=0.05)


def _repos(tmp_path):
    repos = RepositoryBundle.from_storage(db_path=tmp_path / "workflow.db")
    repos.strategy.upsert_strategy({"strategy_id": "legacy_champion", "role": "previous_champion", "status": "active"})
    repos.strategy.upsert_strategy({"strategy_id": "parent_learning_challenger", "role": "champion", "status": "active"})
    return repos


def test_reward_risk_failure_trigger_rollback(tmp_path):
    assert "recent_reward_drop" in RollbackPolicy(_repos(tmp_path / "a"), Tracker(reward=-0.2), _cfg(), None).evaluate_rollback()["reasons"]
    assert "sc_risk_increase" in RollbackPolicy(_repos(tmp_path / "b"), Tracker(reward=0, risk=0.1), _cfg(), None).evaluate_rollback()["reasons"]
    assert "failure_rate_increase" in RollbackPolicy(_repos(tmp_path / "c"), Tracker(reward=0, failure=0.1), _cfg(), None).evaluate_rollback()["reasons"]


def test_rollback_updates_role_and_does_not_delete_model(tmp_path):
    repos = _repos(tmp_path)
    result = RollbackPolicy(repos, Tracker(), _cfg(), None).rollback_to_legacy("manual")
    assert result["rolled_back"] is True
    assert result["deleted_model"] is False
    assert repos.strategy.get_strategy("legacy_champion")["role"] == "champion"
