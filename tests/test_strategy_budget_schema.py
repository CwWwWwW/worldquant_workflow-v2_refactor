from __future__ import annotations

import json

from wq_workflow.strategy.budget_schema import StrategyBudgetAllocation, StrategyBudgetPlan, StrategyBudgetReport, StrategyBudgetRule


def test_strategy_budget_schema_roundtrip_json_safe_and_auto_apply_forced_false():
    rule = StrategyBudgetRule(rule_id="r1", rule_type="baseline_floor", min_ratio=0.4, raw_payload={"x": object()})
    assert StrategyBudgetRule.from_dict(rule.to_dict()).rule_type == "baseline_floor"
    allocation = StrategyBudgetAllocation(allocation_id="a1", plan_id="p1", strategy_id="s", auto_apply_allowed=True, reason_codes=["x"])
    data = allocation.to_dict()
    assert data["auto_apply_allowed"] is False
    assert StrategyBudgetAllocation.from_dict(data).auto_apply_allowed is False
    plan = StrategyBudgetPlan(plan_id="p1", allocations=[allocation], total_suggested_ratio=1.0)
    report = StrategyBudgetReport(report_id="r1", allocations=[allocation])
    json.dumps(plan.to_dict())
    json.dumps(report.to_dict())
    assert "+00:00" in plan.generated_at
