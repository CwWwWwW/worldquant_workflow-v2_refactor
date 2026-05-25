from wq_workflow.strategy.portfolio_repository import StrategyPortfolioRepository
from wq_workflow.strategy.portfolio_schema import StrategyPortfolio, StrategyPortfolioReport, StrategyState, StrategyTransition


def test_strategy_portfolio_repository_crud(tmp_path):
    repo = StrategyPortfolioRepository(db_path=tmp_path / "workflow.db")
    assert repo.initialize()["ok"] is True
    state = StrategyState(strategy_id="s1", recommended_state="challenger")
    assert repo.save_state(state) and repo.save_state(state)
    assert repo.get_state("s1").recommended_state == "challenger"
    assert repo.list_states()
    transition = StrategyTransition(transition_id="t1", strategy_id="s1", to_state="challenger", recommendation="promote_to_challenger", auto_apply_allowed=True)
    assert repo.save_transition(transition)
    assert repo.list_transitions("s1")[0].auto_apply_allowed is False
    portfolio = StrategyPortfolio(portfolio_id="p1", states=[state], transitions=[transition])
    assert repo.save_portfolio(portfolio)
    assert repo.get_latest_portfolio().portfolio_id == "p1"
    report = StrategyPortfolioReport(report_id="r1", strategy_states=[state], recommended_transitions=[transition])
    assert repo.save_report(report)
    assert repo.get_latest_report().report_id == "r1"
