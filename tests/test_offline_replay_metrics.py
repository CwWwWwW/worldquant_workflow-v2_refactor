from wq_workflow.offline.replay_metrics import ReplayMetricsCalculator
from wq_workflow.offline.schema import ReplayComparison, ReplayPolicyDecision, ReplayPolicyMetrics


def test_replay_metrics_observable_only_and_rates():
    calc = ReplayMetricsCalculator(min_observable_samples=30)
    decisions = [
        ReplayPolicyDecision(policy_name="legacy", selected_matches_actual=True, selected_matches_legacy=True, observable_outcome=True, reward=1.0, success=True, platform_sc_abs_max=0.2, quality_passed=True),
        ReplayPolicyDecision(policy_name="legacy", selected_matches_actual=False, selected_matches_legacy=False, observable_outcome=False, reward=None, success=None, reason_codes=["insufficient_counterfactual_evidence"]),
    ]
    metrics = calc.calculate_policy_metrics("r1", decisions)
    assert metrics.sample_count == 2
    assert metrics.observable_count == 1
    assert metrics.coverage_rate == 0.5
    assert metrics.agreement_with_actual_rate == 0.5
    assert metrics.agreement_with_legacy_rate == 0.5
    assert metrics.avg_reward == 1.0
    assert metrics.success_rate == 1.0
    assert metrics.avg_platform_sc_abs_max == 0.2
    assert metrics.quality_pass_rate == 1.0


def test_replay_confidence_and_verdict_are_conservative():
    calc = ReplayMetricsCalculator(min_observable_samples=30)
    assert calc.confidence_from_samples(100, 29) == "insufficient"
    assert calc.confidence_from_samples(100, 30) == "low"
    assert calc.confidence_from_samples(200, 150) == "medium"
    assert calc.confidence_from_samples(600, 501) == "high"
    assert calc.verdict_from_delta(ReplayComparison(confidence="low", reward_delta=1.0, success_rate_delta=0.0, sc_risk_delta=0.2)) == "no_clear_difference"
    assert calc.verdict_from_delta(ReplayComparison(confidence="low", reward_delta=1.0, success_rate_delta=0.0, sc_risk_delta=-0.1)) == "challenger_better"
    assert calc.verdict_from_delta(ReplayComparison(confidence="insufficient", reward_delta=1.0, success_rate_delta=1.0, sc_risk_delta=-1.0)) == "insufficient_evidence"


def test_compare_metrics_delta():
    calc = ReplayMetricsCalculator(min_observable_samples=1)
    comparison = calc.compare_metrics(
        ReplayPolicyMetrics(policy_name="legacy", sample_count=30, observable_count=30, avg_reward=1.0, success_rate=0.5, avg_platform_sc_abs_max=0.3),
        ReplayPolicyMetrics(policy_name="budget_choice", sample_count=30, observable_count=30, avg_reward=1.2, success_rate=0.6, avg_platform_sc_abs_max=0.2),
    )
    assert comparison.reward_delta == 0.19999999999999996
    assert comparison.verdict == "challenger_better"
