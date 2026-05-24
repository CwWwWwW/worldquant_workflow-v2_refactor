from types import SimpleNamespace

from wq_workflow.data.repositories import RepositoryBundle
from wq_workflow.strategy.promotion import PromotionPolicy
from wq_workflow.strategy.registry import StrategyRegistry


class Registry:
    def __init__(self, validation=True):
        self.validation = validation

    def load_active_model(self, task):
        return {"payload": {"validation_passed": self.validation, "model_version": "v1"}}


class Replay:
    def __init__(self, repos, validation=True):
        self.model_registry = Registry(validation)
        self.repos = repos

    def evaluate_task(self, task, model_version=None):
        return self.repos.replay.latest_offline_replay_report(task_name=task, strategy_id=f"{task}_learning_challenger") or {}


class Support:
    def __init__(self, passed=True):
        self.passed = passed

    def check_strategy_support(self, strategy_id):
        return {"support_pass": self.passed, "support_coverage": 1.0 if self.passed else 0.0}


def _cfg(**overrides):
    base = {
        "promotion_require_model_validation_pass": True,
        "promotion_require_offline_replay_pass": True,
        "promotion_min_samples": 2,
        "promotion_min_support_coverage": 0.5,
        "promotion_min_reward_improvement": 0.1,
        "promotion_max_sc_risk_delta": 0.1,
        "promotion_max_failure_rate_delta": 0.1,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _setup(tmp_path, report):
    repos = RepositoryBundle.from_storage(db_path=tmp_path / "workflow.db")
    reg = StrategyRegistry(repos, _cfg(), None)
    reg.ensure_default_strategies()
    repos.strategy.upsert_strategy({"strategy_id": "parent_learning_challenger", "role": "challenger", "status": "active", "task_name": "parent", "model_version": "v1"})
    repos.replay.insert_offline_replay_report({"task_name": "parent", "strategy_id": "parent_learning_challenger", "model_version": "v1", **report})
    return repos


def test_sample_support_replay_reward_risk_failure_block_promotion(tmp_path):
    cases = [
        ({"replay_pass": True, "sample_count": 1, "support_coverage": 1, "estimated_reward_delta": 1, "estimated_sc_risk_delta": 0, "estimated_failure_delta": 0}, "sample_count_below_minimum", True),
        ({"replay_pass": False, "sample_count": 3, "support_coverage": 1, "estimated_reward_delta": 1, "estimated_sc_risk_delta": 0, "estimated_failure_delta": 0}, "offline_replay_fail", True),
        ({"replay_pass": True, "sample_count": 3, "support_coverage": 1, "estimated_reward_delta": 0, "estimated_sc_risk_delta": 0, "estimated_failure_delta": 0}, "reward_improvement_below_minimum", True),
        ({"replay_pass": True, "sample_count": 3, "support_coverage": 1, "estimated_reward_delta": 1, "estimated_sc_risk_delta": 0.2, "estimated_failure_delta": 0}, "sc_risk_delta_above_maximum", True),
        ({"replay_pass": True, "sample_count": 3, "support_coverage": 1, "estimated_reward_delta": 1, "estimated_sc_risk_delta": 0, "estimated_failure_delta": 0.2}, "failure_delta_above_maximum", True),
        ({"replay_pass": True, "sample_count": 3, "support_coverage": 1, "estimated_reward_delta": 1, "estimated_sc_risk_delta": 0, "estimated_failure_delta": 0}, "support_insufficient", False),
    ]
    for idx, (report, reason, support_ok) in enumerate(cases):
        repos = _setup(tmp_path / str(idx), report)
        result = PromotionPolicy(repos, Replay(repos), Support(support_ok), _cfg(), None).evaluate_promotion("parent_learning_challenger")
        assert reason in result["reasons"]
        assert result["promotion_pass"] is False


def test_all_conditions_pass_promotes(tmp_path):
    repos = _setup(tmp_path, {"replay_pass": True, "sample_count": 3, "support_coverage": 1, "estimated_reward_delta": 1, "estimated_sc_risk_delta": 0, "estimated_failure_delta": 0})
    result = PromotionPolicy(repos, Replay(repos), Support(True), _cfg(), None).promote_if_eligible("parent_learning_challenger")
    assert result["promoted"] is True
    assert repos.strategy.get_strategy("parent_learning_challenger")["role"] == "champion"
