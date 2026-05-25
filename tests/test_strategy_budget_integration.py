from __future__ import annotations

import json

from wq_workflow.strategy.budget_allocator import StrategyBudgetAllocator
from wq_workflow.strategy.budget_reporter import StrategyBudgetReporter
from wq_workflow.strategy.portfolio_schema import StrategyState


def test_strategy_budget_integration_fake_portfolio_report(tmp_path):
    plan = StrategyBudgetAllocator().build_budget_plan([
        StrategyState(strategy_id="legacy_baseline", strategy_type="legacy_baseline", recommended_state="champion", confidence="high", risk_level="low"),
        StrategyState(strategy_id="random_exploration", strategy_type="random_exploration", recommended_state="shadow", risk_level="low"),
        StrategyState(strategy_id="disabled_s", strategy_type="manual_or_unknown", recommended_state="disabled", risk_level="low"),
        StrategyState(strategy_id="risk_s", strategy_type="ml_parent", recommended_state="challenger", confidence="high", risk_level="high", sample_count=200, evidence_count=10),
    ], total_budget_hint=100)
    by_id = {a.strategy_id: a for a in plan.allocations}
    assert by_id["legacy_baseline"].suggested_ratio >= 0.40
    assert by_id["random_exploration"].suggested_ratio >= 0.05
    assert by_id["disabled_s"].suggested_ratio == 0
    assert by_id["risk_s"].hard_cap_ratio <= 0.05
    path = tmp_path / "strategy_budget_report.json"
    assert StrategyBudgetReporter(status_path=path).update(plan)["ok"] is True
    assert json.loads(path.read_text(encoding="utf-8"))["total_suggested_ratio"] == plan.total_suggested_ratio
