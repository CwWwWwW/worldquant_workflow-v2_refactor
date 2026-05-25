from __future__ import annotations

import json

from wq_workflow.strategy.budget_reporter import StrategyBudgetReporter
from wq_workflow.strategy.budget_schema import StrategyBudgetAllocation, StrategyBudgetPlan


def test_strategy_budget_reporter_atomic_and_corrupt_recovery(tmp_path):
    path = tmp_path / "strategy_budget_report.json"
    path.write_text("{bad", encoding="utf-8")
    plan = StrategyBudgetPlan(plan_id="p1", total_budget_hint=10, allocations=[StrategyBudgetAllocation(strategy_id="s", suggested_ratio=1.0, auto_apply_allowed=True)])
    status = StrategyBudgetReporter(status_path=path).update(plan)
    assert status["ok"] is True
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["allocations"][0]["auto_apply_allowed"] is False
    assert list(tmp_path.glob("strategy_budget_report.json.corrupt.*.bak"))


def test_strategy_budget_reporter_write_failure_not_fatal(tmp_path):
    reporter = StrategyBudgetReporter(status_path=tmp_path / "status.json")
    reporter._write_atomic = lambda payload: (_ for _ in ()).throw(OSError("boom"))
    status = reporter.update(StrategyBudgetPlan(plan_id="p1"))
    assert status["ok"] is False
