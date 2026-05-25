from wq_workflow.config import load_config


def test_strategy_config_defaults():
    cfg = load_config()
    assert cfg.enable_strategy_registry is True
    assert cfg.strategy_scoreboard_auto_refresh is False
    assert cfg.strategy_registry_mode == "advisory"
    assert cfg.enable_strategy_champion_challenger is False
    assert cfg.enable_strategy_budget_allocator is False
    assert cfg.strategy_budget_allocator_auto_apply is False
