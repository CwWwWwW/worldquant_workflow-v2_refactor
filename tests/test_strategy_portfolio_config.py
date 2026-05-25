from wq_workflow.config import load_config


def test_strategy_portfolio_config_defaults():
    cfg = load_config()
    assert cfg.enable_strategy_champion_challenger is False
    assert cfg.strategy_portfolio_auto_refresh is False
    assert cfg.strategy_portfolio_mode == "advisory"
    assert cfg.strategy_allow_auto_champion_promotion is False
    assert cfg.strategy_transition_auto_apply is False
    assert cfg.enable_strategy_budget_allocator is False
    assert cfg.strategy_budget_allocator_auto_apply is False
    assert cfg.strategy_default_champion == "legacy_baseline"
