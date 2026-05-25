from types import SimpleNamespace

from wq_workflow.strategy.portfolio_service import StrategyPortfolioService
from wq_workflow.strategy.repository import StrategyRepository
from wq_workflow.strategy.schema import StrategyScore, StrategyScoreboard


def _cfg(tmp_path, **overrides):
    base = {
        "storage_db_path": str(tmp_path / "workflow.db"),
        "enable_strategy_champion_challenger": False,
        "strategy_portfolio_auto_refresh": False,
        "strategy_portfolio_mode": "advisory",
        "strategy_portfolio_fail_open": True,
        "strategy_portfolio_status_path": str(tmp_path / "status.json"),
        "strategy_default_champion": "legacy_baseline",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_strategy_portfolio_service_manual_refresh(tmp_path):
    cfg = _cfg(tmp_path)
    srepo = StrategyRepository(db_path=cfg.storage_db_path)
    srepo.initialize()
    srepo.save_scoreboard(StrategyScoreboard(scoreboard_id="b1", scores=[StrategyScore(strategy_id="legacy_baseline", strategy_type="legacy_baseline", confidence="medium", risk_level="low"), StrategyScore(strategy_id="s1", confidence="medium", risk_level="low", sample_count=100)]))
    svc = StrategyPortfolioService(config=cfg, db_path=cfg.storage_db_path, strategy_repository=srepo)
    assert svc.startup_check()["enabled"] is False
    result = svc.refresh_portfolio()
    assert result["ok"] is True
    assert svc.get_latest_portfolio().champion_strategy_id == "legacy_baseline"
    assert svc.get_strategy_state("s1").recommended_state == "challenger"
    assert svc.get_status()["auto_apply_allowed"] is False
