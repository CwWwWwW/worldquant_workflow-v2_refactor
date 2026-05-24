from types import SimpleNamespace

from wq_workflow.data.repositories import RepositoryBundle
from wq_workflow.strategy.budget_allocator import BudgetAllocator
from wq_workflow.strategy.portfolio import StrategyPortfolio
from wq_workflow.strategy.registry import StrategyRegistry


def _cfg(**overrides):
    base = {
        "enable_strategy_portfolio": True,
        "enable_challenger_live_budget": False,
        "strategy_default_champion": "legacy_champion",
        "strategy_challenger_live_budget": 1.0,
        "strategy_random_baseline_budget": 0.0,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _portfolio(tmp_path, cfg):
    repos = RepositoryBundle.from_storage(db_path=tmp_path / "workflow.db")
    registry = StrategyRegistry(repos, cfg, None)
    registry.ensure_default_strategies()
    return StrategyPortfolio(registry, BudgetAllocator(cfg), None, None, None, cfg, None, repos), repos, registry


def test_select_strategy_default_legacy(tmp_path):
    portfolio, _, _ = _portfolio(tmp_path, _cfg(enable_strategy_portfolio=False))
    assert portfolio.select_strategy()["strategy_id"] == "legacy_champion"


def test_challenger_live_disabled_not_selected(tmp_path):
    portfolio, _, _ = _portfolio(tmp_path, _cfg(enable_challenger_live_budget=False))
    assert portfolio.select_strategy()["strategy_id"] == "legacy_champion"


def test_challenger_live_enabled_requires_safety_pass(tmp_path):
    portfolio, repos, _ = _portfolio(tmp_path, _cfg(enable_challenger_live_budget=True))
    assert portfolio.select_strategy()["strategy_id"] == "legacy_champion"
    repos.replay.insert_model_safety_report({"strategy_id": "parent_learning_challenger", "safety_status": "pass", "validation_pass": True, "replay_pass": True, "support_pass": True, "promotion_pass": True})
    selected = {portfolio.select_strategy()["strategy_id"] for _ in range(10)}
    assert "parent_learning_challenger" in selected


def test_record_strategy_decision_writes(tmp_path):
    portfolio, repos, _ = _portfolio(tmp_path, _cfg())
    portfolio.record_strategy_decision({"strategy_id": "legacy_champion"}, {"alpha_id": "a1"}, True, False, 0.5)
    assert repos.strategy.list_strategy_decisions("legacy_champion")[0]["alpha_id"] == "a1"
