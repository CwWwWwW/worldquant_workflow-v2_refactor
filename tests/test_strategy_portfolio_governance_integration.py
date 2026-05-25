from types import SimpleNamespace

from wq_workflow.strategy.portfolio_policy import ChampionChallengerPolicy
from wq_workflow.strategy.schema import StrategyScore


def test_strategy_portfolio_governance_blocked_advisory_only():
    policy = ChampionChallengerPolicy(SimpleNamespace(strategy_default_champion="legacy_baseline"))
    portfolio = policy.evaluate_scores([
        StrategyScore(strategy_id="blocked", confidence="high", risk_level="low", sample_count=1000, risk_flags=["blocked"], raw_payload={"governance_status": "blocked"})
    ])
    state = {s.strategy_id: s for s in portfolio.states}["blocked"]
    transition = {t.strategy_id: t for t in portfolio.transitions}["blocked"]
    assert state.recommended_state == "disabled"
    assert transition.recommendation == "blocked_by_governance"
    assert transition.auto_apply_allowed is False
