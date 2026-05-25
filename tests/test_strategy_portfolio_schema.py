import json

from wq_workflow.strategy.portfolio_schema import StrategyPortfolio, StrategyPortfolioReport, StrategyState, StrategyTransition


def test_strategy_portfolio_schema_roundtrip_json_safe():
    state = StrategyState(strategy_id="s1", strategy_type="manual", current_state="shadow", recommended_state="challenger", reason_codes=["x"], raw_payload={"bad": object()})
    transition = StrategyTransition(transition_id="t1", strategy_id="s1", from_state="shadow", to_state="challenger", recommendation="promote_to_challenger", auto_apply_allowed=True)
    portfolio = StrategyPortfolio(portfolio_id="p1", states=[state], transitions=[transition], warnings=["w"])
    report = StrategyPortfolioReport(report_id="r1", strategy_states=[state], recommended_transitions=[transition])
    assert StrategyState.from_dict(state.to_dict()).strategy_id == "s1"
    assert StrategyTransition.from_dict(transition.to_dict()).auto_apply_allowed is False
    assert StrategyPortfolio.from_dict(portfolio.to_dict()).states[0].recommended_state == "challenger"
    assert StrategyPortfolioReport.from_dict(report.to_dict()).recommended_transitions[0].auto_apply_allowed is False
    json.dumps(portfolio.to_dict())
    assert "+00:00" in state.updated_at
