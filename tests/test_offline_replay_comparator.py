from wq_workflow.offline.baseline_comparator import BaselineComparator
from wq_workflow.offline.replay_metrics import ReplayMetricsCalculator
from wq_workflow.offline.schema import ReplayPolicyMetrics


def test_baseline_comparator_legacy_vs_budget():
    comp = BaselineComparator(calculator=ReplayMetricsCalculator(min_observable_samples=1))
    comparisons = comp.compare(
        "r1",
        "legacy",
        ["budget_choice"],
        [
            ReplayPolicyMetrics(replay_run_id="r1", policy_name="legacy", decision_type=None, sample_count=30, observable_count=30, avg_reward=1.0, success_rate=0.5, avg_platform_sc_abs_max=0.3),
            ReplayPolicyMetrics(replay_run_id="r1", policy_name="budget_choice", decision_type=None, sample_count=30, observable_count=30, avg_reward=1.2, success_rate=0.5, avg_platform_sc_abs_max=0.2),
        ],
    )
    assert comparisons[0].baseline_policy == "legacy"
    assert comparisons[0].challenger_policy == "budget_choice"
    assert comparisons[0].verdict == "challenger_better"


def test_baseline_comparator_insufficient_and_worse():
    comp = BaselineComparator()
    insufficient = comp.compare_policy_pair(
        ReplayPolicyMetrics(policy_name="legacy", sample_count=10, observable_count=10),
        ReplayPolicyMetrics(policy_name="model_choice", sample_count=10, observable_count=10),
    )
    assert insufficient.verdict == "insufficient_evidence"
    worse = BaselineComparator(calculator=ReplayMetricsCalculator(min_observable_samples=1)).compare_policy_pair(
        ReplayPolicyMetrics(policy_name="legacy", sample_count=30, observable_count=30, avg_reward=1.0, success_rate=0.5, avg_platform_sc_abs_max=0.2),
        ReplayPolicyMetrics(policy_name="model_choice", sample_count=30, observable_count=30, avg_reward=0.5, success_rate=0.4, avg_platform_sc_abs_max=0.2),
    )
    assert worse.verdict == "challenger_worse"
