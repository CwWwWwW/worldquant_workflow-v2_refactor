from types import SimpleNamespace

from wq_workflow.strategy.schema import StrategyEvidence, StrategyProfile
from wq_workflow.strategy.scorer import StrategyScorer


def test_strategy_scorer_conservative_rules():
    scorer = StrategyScorer(SimpleNamespace(strategy_score_min_samples=30, strategy_score_medium_samples=100, strategy_score_high_samples=500, strategy_high_sc_abs_max_threshold=0.7))
    profile = StrategyProfile(strategy_id="experiment_budget", strategy_type="experiment_budget")
    assert scorer.score_strategy(profile, []).confidence == "insufficient"
    assert scorer.score_strategy(profile, [StrategyEvidence(strategy_id="experiment_budget", sample_count=50)]).confidence == "low"
    assert scorer.score_strategy(profile, [StrategyEvidence(strategy_id="experiment_budget", sample_count=150)]).confidence == "medium"
    assert scorer.score_strategy(profile, [StrategyEvidence(strategy_id="experiment_budget", sample_count=600, success_rate=0.9, avg_platform_sc_abs_max=0.1)]).confidence == "high"
    high_sc = scorer.score_strategy(profile, [StrategyEvidence(strategy_id="experiment_budget", sample_count=600, avg_platform_sc_abs_max=0.9)])
    assert high_sc.risk_level == "high" and high_sc.recommendation == "risk_limited"
    blocked = scorer.score_strategy(StrategyProfile(strategy_id="governance_safe_policy", strategy_type="governance_safe_policy"), [StrategyEvidence(strategy_id="governance_safe_policy", sample_count=100, risk_flags=["governance_blocked"], governance_status="blocked")])
    assert blocked.recommendation == "blocked_by_governance"
    cf = scorer.score_strategy(StrategyProfile(strategy_id="counterfactual_supported_policy", strategy_type="counterfactual_supported_policy"), [StrategyEvidence(strategy_id="counterfactual_supported_policy", sample_count=100, risk_flags=["high_risk_estimate"], counterfactual_confidence="medium")])
    assert cf.recommendation == "risk_limited"
    assert scorer.score_strategy(StrategyProfile(strategy_id="legacy_baseline", strategy_type="legacy_baseline"), []).recommendation == "keep_baseline"
