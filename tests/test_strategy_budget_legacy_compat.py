from __future__ import annotations


def test_strategy_budget_legacy_imports_compatible():
    from wq_workflow.strategy.budget_allocator import BudgetAllocator, StrategyBudgetAllocator
    from wq_workflow.strategy.champion_challenger import ModelSafetyGate
    from wq_workflow.strategy.portfolio import StrategyPortfolio
    from wq_workflow.strategy.promotion import PromotionPolicy
    from wq_workflow.strategy.rollback import RollbackPolicy

    assert BudgetAllocator is not None
    assert StrategyBudgetAllocator is not None
    assert StrategyPortfolio is not None
    assert ModelSafetyGate is not None
    assert PromotionPolicy is not None
    assert RollbackPolicy is not None
    assert BudgetAllocator(type("Cfg", (), {"enable_strategy_portfolio": False})()).allocate([])  # does not apply real budget
