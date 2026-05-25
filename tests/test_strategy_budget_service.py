from __future__ import annotations

from types import SimpleNamespace

from wq_workflow.strategy.budget_service import StrategyBudgetService
from wq_workflow.strategy.portfolio_schema import StrategyPortfolio, StrategyState


class FakePortfolioService:
    def __init__(self):
        self.portfolio = StrategyPortfolio(states=[StrategyState(strategy_id="legacy_baseline", strategy_type="legacy_baseline", recommended_state="champion")])
        self.refreshed = False

    def get_latest_portfolio(self):
        return self.portfolio

    def refresh_portfolio(self):
        self.refreshed = True
        return {"ok": True}


def _cfg(tmp_path, enabled=False):
    return SimpleNamespace(enable_strategy_budget_allocator=enabled, strategy_budget_auto_refresh=False, strategy_budget_mode="advisory", strategy_budget_status_path=str(tmp_path / "status.json"), storage_db_path=str(tmp_path / "workflow.db"), strategy_budget_fail_open=True, strategy_budget_total_hint=20)


def test_strategy_budget_service_startup_disabled_and_manual_refresh(tmp_path):
    svc = StrategyBudgetService(config=_cfg(tmp_path), portfolio_service=FakePortfolioService())
    assert svc.startup_check()["enabled"] is False
    result = svc.refresh_budget_plan()
    assert result["ok"] is True
    assert svc.get_latest_budget_plan() is not None
    assert svc.get_status()["auto_apply"] is False
