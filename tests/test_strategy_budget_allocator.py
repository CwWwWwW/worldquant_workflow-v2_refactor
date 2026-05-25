from __future__ import annotations

from dataclasses import asdict

from wq_workflow.strategy.budget_allocator import StrategyBudgetAllocator
from wq_workflow.strategy.portfolio_schema import StrategyState


def test_strategy_budget_allocator_builds_normalized_plan_without_mutating_states():
    states = [
        StrategyState(strategy_id="legacy_baseline", strategy_type="legacy_baseline", recommended_state="champion", confidence="high", risk_level="low"),
        StrategyState(strategy_id="challenger", strategy_type="ml_parent", recommended_state="challenger", confidence="high", risk_level="low", score=0.8, sample_count=200, evidence_count=10),
        StrategyState(strategy_id="limited", strategy_type="replay_supported", recommended_state="limited_active", confidence="high", risk_level="low", score=0.9, sample_count=600, evidence_count=20),
        StrategyState(strategy_id="disabled", strategy_type="manual_or_unknown", recommended_state="disabled", confidence="high", risk_level="low"),
    ]
    before = [asdict(s) for s in states]
    plan = StrategyBudgetAllocator().build_budget_plan(states, total_budget_hint=200)
    assert abs(sum(a.suggested_ratio for a in plan.allocations) - 1.0) <= 0.001
    assert all(a.auto_apply_allowed is False for a in plan.allocations)
    assert next(a for a in plan.allocations if a.strategy_id == "disabled").suggested_ratio == 0
    assert next(a for a in plan.allocations if a.strategy_id == "challenger").suggested_ratio <= 0.20
    assert next(a for a in plan.allocations if a.strategy_id == "limited").suggested_ratio <= 0.35
    assert next(a for a in plan.allocations if a.strategy_id == "legacy_baseline").suggested_ratio >= 0.40
    assert [asdict(s) for s in states] == before
