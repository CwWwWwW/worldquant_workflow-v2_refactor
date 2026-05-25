from types import SimpleNamespace

from wq_workflow.strategy.schema import StrategyScore
from wq_workflow.strategy.transition_rules import StrategyTransitionRules


def _score(**kw):
    base = {"strategy_id": "s", "strategy_type": "manual_or_unknown", "sample_count": 100, "confidence": "medium", "risk_level": "low", "total_score": 0.6}
    base.update(kw)
    return StrategyScore(**base)


def test_transition_rules_conservative_states():
    rules = StrategyTransitionRules(SimpleNamespace(strategy_default_champion="legacy_baseline"))
    assert rules.recommend_state(_score(strategy_id="legacy_baseline", strategy_type="legacy_baseline")).to_state == "champion"
    assert rules.recommend_state(_score(strategy_id="random_exploration", strategy_type="random_exploration", sample_count=1)).to_state == "shadow"
    assert rules.recommend_state(_score(sample_count=1, confidence="insufficient")).recommendation == "insufficient_evidence"
    assert rules.recommend_state(_score(confidence="medium", risk_level="low")).to_state == "challenger"
    high = _score(confidence="high", risk_level="low", sample_count=500)
    assert rules.recommend_state(high).to_state == "limited_active"
    flagged = _score(confidence="high", risk_level="low", sample_count=500, risk_flags=["high_sc_risk"])
    assert rules.recommend_state(flagged).to_state != "limited_active"
    blocked = _score(risk_level="blocked", risk_flags=["blocked"])
    tr = rules.recommend_state(blocked)
    assert tr.to_state == "disabled" and tr.allowed is False
    assert tr.auto_apply_allowed is False
