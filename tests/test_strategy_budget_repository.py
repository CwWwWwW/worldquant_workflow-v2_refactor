from __future__ import annotations

import sqlite3

from wq_workflow.strategy.budget_repository import StrategyBudgetRepository
from wq_workflow.strategy.budget_schema import StrategyBudgetAllocation, StrategyBudgetPlan, StrategyBudgetReport, StrategyBudgetRule


def test_strategy_budget_repository_crud(tmp_path):
    repo = StrategyBudgetRepository(conn=sqlite3.connect(tmp_path / "workflow.db"))
    assert repo.initialize()["ok"] is True
    rule = StrategyBudgetRule(rule_id="r1", rule_type="baseline_floor")
    assert repo.save_rule(rule)
    assert repo.save_rule(rule)
    assert len(repo.list_rules()) == 1
    allocation = StrategyBudgetAllocation(allocation_id="a1", plan_id="p1", strategy_id="s", suggested_ratio=1.0)
    assert repo.save_allocation(allocation)
    assert repo.list_allocations(plan_id="p1")[0].auto_apply_allowed is False
    plan = StrategyBudgetPlan(plan_id="p1", allocations=[allocation], total_suggested_ratio=1.0)
    assert repo.save_plan(plan)
    assert repo.get_latest_plan().plan_id == "p1"
    report = StrategyBudgetReport(report_id="rep1", allocations=[allocation])
    assert repo.save_report(report)
    assert repo.get_latest_report().report_id == "rep1"
