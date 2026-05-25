from types import SimpleNamespace

from wq_workflow.strategy.portfolio_policy import ChampionChallengerPolicy
from wq_workflow.strategy.schema import StrategyScore


def test_strategy_portfolio_integration_fake_scores(tmp_path):
    policy = ChampionChallengerPolicy(SimpleNamespace(strategy_default_champion="legacy_baseline"))
    portfolio = policy.evaluate_scores([
        StrategyScore(strategy_id="legacy_baseline", strategy_type="legacy_baseline", confidence="medium", risk_level="low"),
        StrategyScore(strategy_id="medium", confidence="medium", risk_level="medium", sample_count=100),
        StrategyScore(strategy_id="high", confidence="high", risk_level="low", sample_count=500),
        StrategyScore(strategy_id="risky", confidence="high", risk_level="high", sample_count=500),
    ])
    by_id = {s.strategy_id: s for s in portfolio.states}
    assert portfolio.champion_strategy_id == "legacy_baseline"
    assert by_id["medium"].recommended_state == "challenger"
    assert by_id["high"].recommended_state == "limited_active"
    assert by_id["risky"].recommended_state != "limited_active"
