from __future__ import annotations

from types import SimpleNamespace

from wq_workflow.experiment.budget import ExperimentBudgetAllocator
from wq_workflow.experiment.schema import ExperimentSummary


def _summary(arm_id, sample_count=100, success_count=40, failure_count=60, reward=0.0, sc=0.2, q=0.2):
    return ExperimentSummary(
        experiment_id="exp",
        arm_id=arm_id,
        sample_count=sample_count,
        success_count=success_count,
        failure_count=failure_count,
        avg_reward=reward,
        avg_platform_sc_abs_max=sc,
        quality_pass_rate=q,
    )


def test_empty_summaries_fallback_tracking_only():
    plan = ExperimentBudgetAllocator().build_budget_plan("exp", [])
    assert plan.status == "fallback_tracking_only"
    assert plan.allocations == []


def test_protection_caps_and_normalization():
    plan = ExperimentBudgetAllocator().build_budget_plan(
        "exp",
        [
            _summary("legacy_baseline"),
            _summary("random_exploration"),
            _summary("treatment_a", reward=1.0, q=0.6),
            _summary("treatment_b", failure_count=90, sc=0.8),
        ],
    )
    by_arm = {a.arm_id: a for a in plan.allocations}
    assert by_arm["legacy_baseline"].suggested_ratio >= 0.15
    assert by_arm["random_exploration"].suggested_ratio >= 0.05
    assert by_arm["treatment_a"].suggested_ratio <= 0.40
    assert abs(sum(a.suggested_ratio for a in plan.allocations) - 1.0) < 0.0001
    assert "high_failure_rate" in by_arm["treatment_b"].reason_codes
    assert "high_sc_risk" in by_arm["treatment_b"].reason_codes
    assert "positive_reward" in by_arm["treatment_a"].reason_codes
    assert "high_quality_pass_rate" in by_arm["treatment_a"].reason_codes


def test_governance_veto_blocks_arm():
    class Gov:
        def allow_experiment_arm(self, experiment_id, arm_id, context):
            return arm_id != "blocked"

    plan = ExperimentBudgetAllocator().build_budget_plan("exp", [_summary("legacy_baseline"), _summary("blocked")], governance_service=Gov())
    blocked = [a for a in plan.allocations if a.arm_id == "blocked"][0]
    assert blocked.status == "governance_blocked"
    assert blocked.suggested_ratio == 0.0
    assert "governance_veto" in blocked.reason_codes
