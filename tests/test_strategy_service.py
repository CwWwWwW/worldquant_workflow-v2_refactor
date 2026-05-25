from types import SimpleNamespace

from wq_workflow.strategy.service import StrategyService


def test_strategy_service_startup_refresh_status(tmp_path):
    cfg = SimpleNamespace(enable_strategy_registry=True, strategy_scoreboard_status_path=str(tmp_path / "status.json"), strategy_registry_mode="advisory", strategy_scoreboard_auto_refresh=False, strategy_fail_open=True, storage_db_path=str(tmp_path / "workflow.db"))
    svc = StrategyService(config=cfg, db_path=cfg.storage_db_path)
    assert svc.startup_check()["ok"] is True
    result = svc.refresh_scoreboard()
    assert result["ok"] is True
    assert svc.get_latest_scoreboard() is not None
    assert svc.get_status()["enabled"] is True
    assert svc.list_strategy_scores()


def test_strategy_service_disabled_no_refresh(tmp_path):
    cfg = SimpleNamespace(enable_strategy_registry=False, strategy_registry_mode="advisory", strategy_scoreboard_status_path=str(tmp_path / "status.json"), storage_db_path=str(tmp_path / "workflow.db"))
    svc = StrategyService(config=cfg, db_path=cfg.storage_db_path)
    assert svc.startup_check()["enabled"] is False
    assert svc.refresh_scoreboard()["refreshed"] is False
