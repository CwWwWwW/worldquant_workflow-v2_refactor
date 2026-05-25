from __future__ import annotations


def test_strategy_budget_config_defaults():
    from wq_workflow.config import load_config

    cfg = load_config()
    assert cfg.enable_strategy_budget_allocator is False
    assert cfg.strategy_budget_auto_refresh is False
    assert cfg.strategy_budget_mode == "advisory"
    assert cfg.strategy_budget_auto_apply is False
    assert cfg.strategy_budget_allocator_auto_apply is False
    assert cfg.strategy_budget_legacy_min_ratio >= 0.40
    assert cfg.strategy_budget_exploration_min_ratio >= 0.05
