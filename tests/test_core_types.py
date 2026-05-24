from __future__ import annotations

from wq_workflow.core_types import (
    CandidateDraft,
    DecisionSnapshot,
    PersistResult,
    PlatformSCResult,
    QualityResult,
    RewardResult,
    ServiceResult,
    SimulationResult,
    WorkflowError,
)


def roundtrip(cls, payload):
    obj = cls.from_dict(payload)
    data = obj.to_dict()
    obj2 = cls.from_dict(data)
    assert obj2.to_dict() == data
    return obj


def test_core_type_roundtrips():
    roundtrip(CandidateDraft, {"alpha_id": "a1", "expression": "rank(close)", "ignored": 1})
    roundtrip(SimulationResult, {"alpha_id": "a1", "ok": True, "metrics": {"sharpe": 1.2}})
    sc = roundtrip(PlatformSCResult, {"status": "complete", "max": 0.1, "min": -0.2, "abs_max": 0.2})
    assert sc.to_metrics()["platform_sc_abs_max"] == 0.2
    roundtrip(QualityResult, {"passed": True, "pass_count": 3})
    roundtrip(RewardResult, {"reward": 1.0, "reward_components": {"x": 1}})
    roundtrip(PersistResult, {"ok": True, "sqlite_saved": True})
    roundtrip(DecisionSnapshot, {"decision_id": "d1", "decision_type": "policy"})
    err = roundtrip(WorkflowError, {"code": "X", "message": "bad", "severity": "warning"})
    assert err.recoverable is True


def test_service_result_error_and_warning_expression():
    res = ServiceResult(ok=False, error="failed", warnings=["soft"], source="unit")
    assert res.to_dict()["error"] == "failed"
    assert res.to_dict()["warnings"] == ["soft"]
