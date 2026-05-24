from types import SimpleNamespace

from wq_workflow.data.repositories import RepositoryBundle
from wq_workflow.strategy.registry import StrategyRegistry


def test_strategy_registry_defaults_and_role_updates(tmp_path):
    repos = RepositoryBundle.from_storage(db_path=tmp_path / "workflow.db")
    registry = StrategyRegistry(repos, SimpleNamespace(), None)
    registry.ensure_default_strategies()
    champion = registry.get_champion()
    assert champion["strategy_id"] == "legacy_champion"
    assert {s["strategy_id"] for s in registry.list_challengers()} >= {"parent_learning_challenger", "policy_learning_challenger"}

    registry.update_role("parent_learning_challenger", "champion", "test")
    assert registry.get_champion()["strategy_id"] == "parent_learning_challenger"
    registry.deactivate_strategy("parent_learning_challenger", "test")
    assert repos.strategy.get_strategy("parent_learning_challenger")["status"] == "inactive"
