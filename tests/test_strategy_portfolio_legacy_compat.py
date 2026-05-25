def test_strategy_portfolio_legacy_imports_compatible():
    from wq_workflow.strategy.champion_challenger import ModelSafetyGate, ChampionChallengerPolicy, StrategyPortfolioService
    from wq_workflow.strategy.portfolio import StrategyPortfolio
    from wq_workflow.strategy.budget_allocator import BudgetAllocator
    from wq_workflow.strategy.promotion import PromotionPolicy
    from wq_workflow.strategy.rollback import RollbackPolicy

    assert ModelSafetyGate is not None
    assert ChampionChallengerPolicy is not None
    assert StrategyPortfolioService is not None
    assert StrategyPortfolio is not None
    assert BudgetAllocator is not None
    assert PromotionPolicy is not None
    assert RollbackPolicy is not None
