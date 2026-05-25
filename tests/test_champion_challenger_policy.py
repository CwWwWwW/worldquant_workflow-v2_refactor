from types import SimpleNamespace

from wq_workflow.strategy.portfolio_policy import ChampionChallengerPolicy
from wq_workflow.strategy.schema import StrategyScore


def test_policy_keeps_legacy_baseline_champion_and_blocks_risky():
    policy = ChampionChallengerPolicy(SimpleNamespace(strategy_default_champion="legacy_baseline"))
    scores = [
        StrategyScore(strategy_id="legacy_baseline", strategy_type="legacy_baseline", total_score=0.4, confidence="medium", risk_level="low"),
        StrategyScore(strategy_id="better", total_score=0.99, confidence="high", risk_level="low", sample_count=1000),
        StrategyScore(strategy_id="blocked", total_score=0.1, confidence="high", risk_level="blocked", sample_count=1000),
    ]
    portfolio = policy.evaluate_scores(scores)
    by_id = {s.strategy_id: s for s in portfolio.states}
    assert portfolio.champion_strategy_id == "legacy_baseline"
    assert by_id["legacy_baseline"].recommended_state == "champion"
    assert by_id["better"].recommended_state == "limited_active"
    assert by_id["blocked"].recommended_state == "disabled"
    assert all(t.auto_apply_allowed is False for t in portfolio.transitions)
