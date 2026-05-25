from __future__ import annotations

import sqlite3

from wq_workflow.strategy.budget_service import StrategyBudgetService
from wq_workflow.strategy.portfolio_repository import StrategyPortfolioRepository
from wq_workflow.strategy.portfolio_schema import StrategyPortfolio, StrategyState


def test_strategy_budget_reads_latest_portfolio_without_modifying_it(tmp_path):
    conn = sqlite3.connect(tmp_path / "workflow.db")
    portfolio_repo = StrategyPortfolioRepository(conn=conn)
    state = StrategyState(strategy_id="legacy_baseline", strategy_type="legacy_baseline", recommended_state="champion")
    portfolio_repo.save_portfolio(StrategyPortfolio(portfolio_id="pf1", states=[state]))
    cfg = type("Cfg", (), {"enable_strategy_budget_allocator": False, "strategy_budget_auto_refresh": False, "strategy_budget_status_path": str(tmp_path / "status.json"), "storage_db_path": str(tmp_path / "workflow.db"), "strategy_budget_mode": "advisory", "strategy_budget_total_hint": 10, "strategy_budget_fail_open": True})()
    svc = StrategyBudgetService(config=cfg, repository=None, portfolio_repository=portfolio_repo, db_path=tmp_path / "workflow.db")
    assert svc.refresh_budget_plan()["ok"] is True
    assert portfolio_repo.get_latest_portfolio().states[0].recommended_state == "champion"
