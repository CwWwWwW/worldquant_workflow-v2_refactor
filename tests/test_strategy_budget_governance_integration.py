from __future__ import annotations

from wq_workflow.strategy.budget_allocator import StrategyBudgetAllocator
from wq_workflow.strategy.portfolio_schema import StrategyState


def test_strategy_budget_governance_blocked_advisory_only():
    plan = StrategyBudgetAllocator().build_budget_plan([
        StrategyState(strategy_id="legacy_baseline", strategy_type="legacy_baseline", recommended_state="champion", risk_level="low"),
        StrategyState(strategy_id="blocked", strategy_type="ml_parent", recommended_state="challenger", governance_status="blocked", risk_flags=["governance_blocked"]),
    ])
    allocation = next(a for a in plan.allocations if a.strategy_id == "blocked")
    assert allocation.suggested_ratio == 0
    assert "governance_blocked_budget_zero" in allocation.reason_codes
    assert allocation.auto_apply_allowed is False
