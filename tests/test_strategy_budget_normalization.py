from __future__ import annotations

from wq_workflow.strategy.budget_allocator import StrategyBudgetAllocator
from wq_workflow.strategy.portfolio_schema import StrategyState


def test_strategy_budget_normalization_preserves_floors_caps_and_fallback():
    allocator = StrategyBudgetAllocator()
    plan = allocator.build_budget_plan([
        StrategyState(strategy_id="legacy_baseline", strategy_type="legacy_baseline", recommended_state="champion", risk_level="low"),
        StrategyState(strategy_id="random_exploration", strategy_type="random_exploration", recommended_state="shadow", risk_level="low"),
        StrategyState(strategy_id="challenger", strategy_type="ml_parent", recommended_state="challenger", confidence="high", risk_level="low", sample_count=200, evidence_count=10),
    ])
    assert abs(sum(a.suggested_ratio for a in plan.allocations) - 1.0) <= 0.001
    assert next(a for a in plan.allocations if a.strategy_id == "legacy_baseline").suggested_ratio >= 0.40
    assert next(a for a in plan.allocations if a.strategy_id == "random_exploration").suggested_ratio >= 0.05
    assert next(a for a in plan.allocations if a.strategy_id == "challenger").suggested_ratio <= 0.35
    fallback = allocator.build_budget_plan([StrategyState(strategy_id="blocked", recommended_state="disabled", risk_level="blocked")])
    assert abs(sum(a.suggested_ratio for a in fallback.allocations) - 1.0) <= 0.001
    assert next(a for a in fallback.allocations if a.strategy_id == "legacy_baseline").suggested_ratio >= 0.90
