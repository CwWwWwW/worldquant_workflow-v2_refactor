from __future__ import annotations

import json

from wq_workflow.experiment.budget import (
    ArmRecommendation,
    ExperimentBudgetAllocation,
    ExperimentBudgetPlan,
    ExperimentBudgetRule,
    ExperimentBudgetSnapshot,
)


def test_budget_dataclasses_roundtrip_json_safe():
    rule = ExperimentBudgetRule("r1", "rule", raw_payload={"bad": float("nan")})
    allocation = ExperimentBudgetAllocation(
        allocation_id="a1",
        experiment_id="exp",
        arm_id="legacy_baseline",
        suggested_ratio=0.2,
        reason_codes=["protect_legacy_baseline"],
    )
    plan = ExperimentBudgetPlan("p1", "exp", allocations=[allocation], total_budget_hint=200)
    snapshot = ExperimentBudgetSnapshot("s1", "p1", "exp", allocations_json=[allocation.to_dict()])
    rec = ArmRecommendation("r1", "exp", "legacy_baseline", 0.2, ["protect_legacy_baseline"])

    for obj, cls in [
        (rule, ExperimentBudgetRule),
        (allocation, ExperimentBudgetAllocation),
        (plan, ExperimentBudgetPlan),
        (snapshot, ExperimentBudgetSnapshot),
        (rec, ArmRecommendation),
    ]:
        payload = obj.to_dict()
        json.dumps(payload, allow_nan=False)
        restored = cls.from_dict(payload)
        assert restored.to_dict()
        assert "+00:00" in restored.to_dict().get("created_at", "+00:00") or restored.to_dict().get("created_at")
