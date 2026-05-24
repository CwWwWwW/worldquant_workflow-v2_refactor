from __future__ import annotations

from wq_workflow.experiment.policy import ExperimentBudgetPolicy
from wq_workflow.experiment.schema import ExperimentSummary


def test_budget_policy_rules():
    policy = ExperimentBudgetPolicy()
    low = ExperimentSummary("exp", "a", sample_count=2)
    risky = ExperimentSummary("exp", "b", sample_count=100, failure_count=80, avg_platform_sc_abs_max=0.8, quality_pass_rate=0.4, avg_reward=0.1)
    assert policy.is_insufficient_sample(low)
    assert policy.is_high_failure(risky)
    assert policy.is_high_sc_risk(risky)
    assert policy.is_high_quality(risky)
    assert policy.clamp_ratio(2, 0.1, 0.4) == 0.4
    codes = policy.reason_codes(risky)
    assert {"high_failure_rate", "high_sc_risk", "positive_reward", "high_quality_pass_rate"} <= set(codes)
