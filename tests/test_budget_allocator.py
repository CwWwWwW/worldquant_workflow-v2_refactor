from types import SimpleNamespace

from wq_workflow.strategy.budget_allocator import BudgetAllocator


def _cfg(**overrides):
    base = {
        "enable_strategy_portfolio": True,
        "enable_challenger_live_budget": False,
        "strategy_default_champion": "legacy_champion",
        "strategy_challenger_live_budget": 0.2,
        "strategy_random_baseline_budget": 0.1,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


STRATEGIES = [
    {"strategy_id": "legacy_champion", "role": "champion", "status": "active"},
    {"strategy_id": "parent_learning_challenger", "role": "challenger", "status": "active", "safety_pass": True},
    {"strategy_id": "policy_learning_challenger", "role": "challenger", "status": "active", "safety_pass": False},
    {"strategy_id": "random_baseline", "role": "baseline", "status": "active"},
]


def test_portfolio_disabled_legacy_100():
    alloc = BudgetAllocator(_cfg(enable_strategy_portfolio=False)).allocate(STRATEGIES)
    assert alloc["legacy_champion"] == 1.0
    assert alloc["parent_learning_challenger"] == 0.0


def test_challenger_live_disabled_champion_100():
    alloc = BudgetAllocator(_cfg(enable_challenger_live_budget=False)).allocate(STRATEGIES)
    assert alloc["legacy_champion"] == 1.0
    assert alloc["parent_learning_challenger"] == 0.0


def test_challenger_live_enabled_only_safe_gets_budget():
    alloc = BudgetAllocator(_cfg(enable_challenger_live_budget=True)).allocate(STRATEGIES)
    assert abs(sum(alloc.values()) - 1.0) < 1e-9
    assert abs(alloc["parent_learning_challenger"] - 0.2) < 1e-9
    assert alloc["policy_learning_challenger"] == 0.0
    assert abs(alloc["random_baseline"] - 0.1) < 1e-9
