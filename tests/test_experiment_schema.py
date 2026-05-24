from __future__ import annotations

from wq_workflow.experiment.schema import (
    ExperimentAssignment,
    ExperimentArm,
    ExperimentHypothesis,
    ExperimentPlan,
    ExperimentResult,
    ExperimentSummary,
)


def test_experiment_schema_roundtrips():
    hypothesis = ExperimentHypothesis("h1", "name", "desc", "template_family", "mean_reversion", "higher reward", raw_payload={"x": object()})
    arm = ExperimentArm("a1", "e1", "arm", "treatment", "template_family", "mean_reversion", 0.5, False, {"n": 1})
    plan = ExperimentPlan("e1", "plan", "active", hypothesis, [arm], raw_payload={"phase": "4A"})
    assignment = ExperimentAssignment("as1", "e1", "a1", alpha_id="alpha", expression_hash="hash", raw_payload={"candidate": True})
    result = ExperimentResult("r1", "as1", "e1", "a1", alpha_id="alpha", success=True, reward=1.2, sharpe=1.3, quality_passed=True)
    summary = ExperimentSummary("e1", "a1", sample_count=1, success_count=1, avg_reward=1.2)

    assert ExperimentHypothesis.from_dict(hypothesis.to_dict()).hypothesis_id == "h1"
    assert ExperimentArm.from_dict(arm.to_dict()).arm_id == "a1"
    assert ExperimentPlan.from_dict(plan.to_dict()).arms[0].arm_id == "a1"
    assert ExperimentAssignment.from_dict(assignment.to_dict()).alpha_id == "alpha"
    assert ExperimentResult.from_dict(result.to_dict()).success is True
    assert ExperimentSummary.from_dict(summary.to_dict()).sample_count == 1
    assert isinstance(hypothesis.to_dict()["raw_payload"], dict)
