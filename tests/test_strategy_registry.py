from types import SimpleNamespace

from wq_workflow.data.repositories import RepositoryBundle
from wq_workflow.strategy.registry import StrategyRegistry
from wq_workflow.strategy.schema import StrategyProfile


def test_strategy_registry_default_profiles_and_legacy_compat(tmp_path):
    repos = RepositoryBundle.from_storage(db_path=tmp_path / "workflow.db")
    registry = StrategyRegistry(repos, SimpleNamespace(), None)
    registry.ensure_default_strategies()
    ids = {p.strategy_id for p in registry.default_profiles()}
    assert ids >= {"legacy_baseline", "random_exploration", "experiment_budget", "ml_parent_policy", "ml_mutation_policy", "replay_supported_policy", "counterfactual_supported_policy", "governance_safe_policy", "manual_or_unknown"}
    assert all(p.advisory_only for p in registry.default_profiles())
    registry.register_strategy(StrategyProfile(strategy_id="custom", strategy_type="manual_or_unknown"))
    assert registry.get_strategy("custom").strategy_id == "custom"
    assert registry.list_strategies("manual_or_unknown")
    assert registry.get_champion()["strategy_id"] == "legacy_champion"
    assert {s["strategy_id"] for s in registry.list_challengers()} >= {"parent_learning_challenger", "policy_learning_challenger"}
    registry.update_role("parent_learning_challenger", "champion", "test")
    assert registry.get_champion()["strategy_id"] == "parent_learning_challenger"
    registry.deactivate_strategy("parent_learning_challenger", "test")
    assert repos.strategy.get_strategy("parent_learning_challenger")["status"] == "inactive"
