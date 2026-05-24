from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from typing import Any

from wq_workflow.data.json_utils import to_jsonable

from .policy import ExperimentBudgetPolicy
from .schema import ExperimentSummary, utc_now_iso


BUDGET_PLAN_STATUSES = {"advisory", "active", "paused", "invalid", "fallback_tracking_only"}
BUDGET_ALLOCATION_STATUSES = {"active", "disabled", "insufficient_samples", "governance_blocked", "capped", "protected"}
LEGACY_ARM_ID = "legacy_baseline"
RANDOM_ARM_ID = "random_exploration"


@dataclass
class ExperimentBudgetRule:
    rule_id: str
    name: str
    enabled: bool = True
    min_samples: int = 0
    weight: float = 1.0
    raw_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _clean_dict(asdict(self))

    @classmethod
    def from_dict(cls, data: Any) -> "ExperimentBudgetRule":
        source = data if isinstance(data, dict) else {}
        return cls(
            rule_id=str(source.get("rule_id") or ""),
            name=str(source.get("name") or ""),
            enabled=bool(source.get("enabled", True)),
            min_samples=_int(source.get("min_samples"), 0),
            weight=_float(source.get("weight"), 1.0) or 1.0,
            raw_payload=_clean_dict(source.get("raw_payload") or {}),
        )


@dataclass
class ExperimentBudgetAllocation:
    allocation_id: str
    experiment_id: str
    arm_id: str
    suggested_ratio: float
    min_ratio: float = 0.0
    max_ratio: float = 1.0
    sample_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    avg_reward: float | None = None
    avg_platform_sc_abs_max: float | None = None
    quality_pass_rate: float | None = None
    reason_codes: list[str] = field(default_factory=list)
    governance_allowed: bool = True
    status: str = "active"
    created_at: str = field(default_factory=utc_now_iso)
    raw_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["suggested_ratio"] = _ratio(self.suggested_ratio)
        data["min_ratio"] = _ratio(self.min_ratio)
        data["max_ratio"] = _ratio(self.max_ratio)
        data["reason_codes"] = [str(item) for item in (self.reason_codes or [])]
        data["raw_payload"] = _clean_dict(self.raw_payload)
        return _clean_dict(data)

    @classmethod
    def from_dict(cls, data: Any) -> "ExperimentBudgetAllocation":
        source = data if isinstance(data, dict) else {}
        return cls(
            allocation_id=str(source.get("allocation_id") or ""),
            experiment_id=str(source.get("experiment_id") or ""),
            arm_id=str(source.get("arm_id") or ""),
            suggested_ratio=_ratio(source.get("suggested_ratio")),
            min_ratio=_ratio(source.get("min_ratio")),
            max_ratio=_ratio(source.get("max_ratio"), 1.0),
            sample_count=_int(source.get("sample_count"), 0),
            success_count=_int(source.get("success_count"), 0),
            failure_count=_int(source.get("failure_count"), 0),
            avg_reward=_nullable_float(source.get("avg_reward")),
            avg_platform_sc_abs_max=_nullable_float(source.get("avg_platform_sc_abs_max")),
            quality_pass_rate=_nullable_float(source.get("quality_pass_rate")),
            reason_codes=[str(item) for item in (source.get("reason_codes") or [])],
            governance_allowed=bool(source.get("governance_allowed", True)),
            status=str(source.get("status") or "active"),
            created_at=str(source.get("created_at") or utc_now_iso()),
            raw_payload=_clean_dict(source.get("raw_payload") or {}),
        )


@dataclass
class ExperimentBudgetPlan:
    budget_plan_id: str
    experiment_id: str
    status: str = "advisory"
    total_budget_hint: int | None = None
    allocations: list[ExperimentBudgetAllocation] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    generated_by: str = "phase4b_budget_allocator"
    raw_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _clean_dict(
            {
                "budget_plan_id": self.budget_plan_id,
                "experiment_id": self.experiment_id,
                "status": self.status,
                "total_budget_hint": self.total_budget_hint,
                "allocations": [item.to_dict() for item in self.allocations],
                "created_at": self.created_at,
                "updated_at": self.updated_at,
                "generated_by": self.generated_by,
                "raw_payload": _clean_dict(self.raw_payload),
            }
        )

    @classmethod
    def from_dict(cls, data: Any) -> "ExperimentBudgetPlan":
        source = data if isinstance(data, dict) else {}
        return cls(
            budget_plan_id=str(source.get("budget_plan_id") or ""),
            experiment_id=str(source.get("experiment_id") or ""),
            status=str(source.get("status") or "advisory"),
            total_budget_hint=_nullable_int(source.get("total_budget_hint")),
            allocations=[
                item if isinstance(item, ExperimentBudgetAllocation) else ExperimentBudgetAllocation.from_dict(item)
                for item in (source.get("allocations") or [])
            ],
            created_at=str(source.get("created_at") or utc_now_iso()),
            updated_at=str(source.get("updated_at") or utc_now_iso()),
            generated_by=str(source.get("generated_by") or "phase4b_budget_allocator"),
            raw_payload=_clean_dict(source.get("raw_payload") or {}),
        )


@dataclass
class ExperimentBudgetSnapshot:
    snapshot_id: str
    budget_plan_id: str
    experiment_id: str
    total_budget_hint: int | None = None
    allocations_json: list[dict[str, Any]] | dict[str, Any] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now_iso)
    raw_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _clean_dict(asdict(self))

    @classmethod
    def from_dict(cls, data: Any) -> "ExperimentBudgetSnapshot":
        source = data if isinstance(data, dict) else {}
        allocations = source.get("allocations_json")
        if not isinstance(allocations, (list, dict)):
            allocations = []
        return cls(
            snapshot_id=str(source.get("snapshot_id") or ""),
            budget_plan_id=str(source.get("budget_plan_id") or ""),
            experiment_id=str(source.get("experiment_id") or ""),
            total_budget_hint=_nullable_int(source.get("total_budget_hint")),
            allocations_json=to_jsonable(allocations),
            created_at=str(source.get("created_at") or utc_now_iso()),
            raw_payload=_clean_dict(source.get("raw_payload") or {}),
        )


@dataclass
class ArmRecommendation:
    recommendation_id: str
    experiment_id: str
    arm_id: str
    suggested_ratio: float
    reason_codes: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now_iso)
    raw_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["suggested_ratio"] = _ratio(self.suggested_ratio)
        data["reason_codes"] = [str(item) for item in (self.reason_codes or [])]
        data["raw_payload"] = _clean_dict(self.raw_payload)
        return _clean_dict(data)

    @classmethod
    def from_dict(cls, data: Any) -> "ArmRecommendation":
        source = data if isinstance(data, dict) else {}
        return cls(
            recommendation_id=str(source.get("recommendation_id") or ""),
            experiment_id=str(source.get("experiment_id") or ""),
            arm_id=str(source.get("arm_id") or ""),
            suggested_ratio=_ratio(source.get("suggested_ratio")),
            reason_codes=[str(item) for item in (source.get("reason_codes") or [])],
            created_at=str(source.get("created_at") or utc_now_iso()),
            raw_payload=_clean_dict(source.get("raw_payload") or {}),
        )


class ExperimentBudgetAllocator:
    def __init__(self, *, config: Any | None = None, policy: ExperimentBudgetPolicy | None = None, logger: Any | None = None) -> None:
        self.config = config
        self.policy = policy or ExperimentBudgetPolicy(config=config)
        self.logger = logger

    def build_budget_plan(
        self,
        experiment_id: str,
        summaries: list[ExperimentSummary] | list[Any] | None,
        total_budget_hint: int | None = None,
        governance_service: Any | None = None,
    ) -> ExperimentBudgetPlan:
        now = utc_now_iso()
        clean_summaries = [item if isinstance(item, ExperimentSummary) else ExperimentSummary.from_dict(item) for item in (summaries or [])]
        plan = ExperimentBudgetPlan(
            budget_plan_id=_stable_id("budget_plan", experiment_id, now),
            experiment_id=str(experiment_id or ""),
            status="advisory",
            total_budget_hint=total_budget_hint,
            created_at=now,
            updated_at=now,
            raw_payload={"mode": "advisory", "phase": "4B"},
        )
        if not clean_summaries:
            plan.status = "fallback_tracking_only"
            plan.raw_payload["reason"] = "no_experiment_summaries"
            return plan
        clean_summaries = self._with_protected_baselines(str(experiment_id or ""), clean_summaries)
        plan.allocations = [self._allocation_from_summary(summary) for summary in clean_summaries]
        self.apply_governance_rules(plan.allocations, governance_service)
        self.apply_protection_rules(plan.allocations)
        self.apply_performance_rules(plan.allocations)
        plan.allocations = self.normalize_allocations(plan.allocations)
        return plan

    def normalize_allocations(self, allocations: list[ExperimentBudgetAllocation]) -> list[ExperimentBudgetAllocation]:
        eligible = [a for a in allocations if a.status not in {"disabled", "governance_blocked"} and a.governance_allowed and a.max_ratio > 0]
        if not eligible:
            for allocation in allocations:
                allocation.suggested_ratio = 0.0
            return allocations
        min_sum = sum(max(0.0, min(a.min_ratio, a.max_ratio)) for a in eligible)
        if min_sum >= 1.0:
            for allocation in eligible:
                allocation.suggested_ratio = max(0.0, min(allocation.min_ratio, allocation.max_ratio)) / min_sum
            return allocations
        assigned: dict[str, float] = {a.allocation_id: max(0.0, min(a.min_ratio, a.max_ratio)) for a in eligible}
        remaining = 1.0 - sum(assigned.values())
        pending = list(eligible)
        while pending and remaining > 1e-9:
            total_weight = sum(max(0.0, a.suggested_ratio) for a in pending) or float(len(pending))
            next_pending: list[ExperimentBudgetAllocation] = []
            used = 0.0
            for allocation in pending:
                weight = max(0.0, allocation.suggested_ratio) or 1.0
                desired = remaining * (weight / total_weight)
                capacity = max(0.0, allocation.max_ratio - assigned[allocation.allocation_id])
                add = min(desired, capacity)
                assigned[allocation.allocation_id] += add
                used += add
                if capacity - add > 1e-9:
                    next_pending.append(allocation)
                elif allocation.max_ratio < 1.0 and "cap_single_arm_budget" not in allocation.reason_codes:
                    allocation.reason_codes.append("cap_single_arm_budget")
                    allocation.status = "capped"
            if used <= 1e-9:
                break
            remaining -= used
            pending = next_pending
        for allocation in allocations:
            if allocation in eligible:
                allocation.suggested_ratio = round(max(0.0, assigned.get(allocation.allocation_id, 0.0)), 10)
            else:
                allocation.suggested_ratio = 0.0
        return allocations

    def apply_protection_rules(self, allocations: list[ExperimentBudgetAllocation]) -> None:
        for allocation in allocations:
            if allocation.arm_id == LEGACY_ARM_ID:
                allocation.min_ratio = max(allocation.min_ratio, self.policy.legacy_min_ratio)
                allocation.reason_codes.append("protect_legacy_baseline")
                if allocation.status != "governance_blocked":
                    allocation.status = "protected"
            elif allocation.arm_id == RANDOM_ARM_ID:
                allocation.min_ratio = max(allocation.min_ratio, self.policy.random_min_ratio)
                allocation.reason_codes.append("protect_random_exploration")
                if allocation.status != "governance_blocked":
                    allocation.status = "protected"
            else:
                allocation.max_ratio = min(allocation.max_ratio, self.policy.treatment_max_ratio)

    def apply_performance_rules(self, allocations: list[ExperimentBudgetAllocation]) -> None:
        for allocation in allocations:
            if "insufficient_samples" in allocation.reason_codes and allocation.status == "active":
                allocation.status = "insufficient_samples"
            if "high_failure_rate" in allocation.reason_codes:
                allocation.raw_payload["failure_penalty_applied"] = True
            if "high_sc_risk" in allocation.reason_codes:
                allocation.raw_payload["sc_risk_penalty_applied"] = True

    def apply_governance_rules(self, allocations: list[ExperimentBudgetAllocation], governance_service: Any | None = None) -> None:
        if governance_service is None or not hasattr(governance_service, "allow_experiment_arm"):
            return
        for allocation in allocations:
            try:
                verdict = governance_service.allow_experiment_arm(
                    allocation.experiment_id,
                    allocation.arm_id,
                    {"allocation": allocation.to_dict(), "mode": "advisory"},
                )
                allowed = _verdict_allowed(verdict)
            except Exception as exc:
                allocation.raw_payload["governance_warning"] = str(exc)
                allowed = True
            allocation.governance_allowed = bool(allowed)
            if not allowed:
                allocation.status = "governance_blocked"
                allocation.suggested_ratio = 0.0
                allocation.reason_codes.append("governance_veto")

    def _allocation_from_summary(self, summary: ExperimentSummary) -> ExperimentBudgetAllocation:
        reasons = self.policy.reason_codes(summary)
        score = self.policy.score_arm(summary)
        status = "insufficient_samples" if "insufficient_samples" in reasons else "active"
        return ExperimentBudgetAllocation(
            allocation_id=_stable_id("budget_allocation", summary.experiment_id, summary.arm_id),
            experiment_id=summary.experiment_id,
            arm_id=summary.arm_id,
            suggested_ratio=score,
            sample_count=summary.sample_count,
            success_count=summary.success_count,
            failure_count=summary.failure_count,
            avg_reward=summary.avg_reward,
            avg_platform_sc_abs_max=summary.avg_platform_sc_abs_max,
            quality_pass_rate=summary.quality_pass_rate,
            reason_codes=reasons,
            status=status,
            raw_payload={"score": score},
        )

    def _with_protected_baselines(self, experiment_id: str, summaries: list[ExperimentSummary]) -> list[ExperimentSummary]:
        by_arm = {summary.arm_id for summary in summaries}
        protected = list(summaries)
        if LEGACY_ARM_ID not in by_arm:
            protected.append(ExperimentSummary(experiment_id=experiment_id, arm_id=LEGACY_ARM_ID, raw_payload={"synthetic_budget_protection": True}))
        if RANDOM_ARM_ID not in by_arm:
            protected.append(ExperimentSummary(experiment_id=experiment_id, arm_id=RANDOM_ARM_ID, raw_payload={"synthetic_budget_protection": True}))
        return protected


def snapshot_from_plan(plan: ExperimentBudgetPlan) -> ExperimentBudgetSnapshot:
    return ExperimentBudgetSnapshot(
        snapshot_id=_stable_id("budget_snapshot", plan.budget_plan_id, utc_now_iso()),
        budget_plan_id=plan.budget_plan_id,
        experiment_id=plan.experiment_id,
        total_budget_hint=plan.total_budget_hint,
        allocations_json=[allocation.to_dict() for allocation in plan.allocations],
        raw_payload={"status": plan.status, "generated_by": plan.generated_by},
    )


def _stable_id(prefix: str, *parts: Any) -> str:
    digest = hashlib.sha256("|".join(str(part) for part in parts).encode("utf-8", errors="replace")).hexdigest()[:24]
    return f"{prefix}:{digest}"


def _verdict_allowed(verdict: Any) -> bool:
    if isinstance(verdict, bool):
        return verdict
    if isinstance(verdict, dict):
        if "allowed" in verdict:
            return bool(verdict.get("allowed"))
        if "ok" in verdict:
            return bool(verdict.get("ok"))
    return bool(verdict)


def _clean_dict(value: Any) -> dict[str, Any]:
    cleaned = to_jsonable(value if isinstance(value, dict) else {})
    return cleaned if isinstance(cleaned, dict) else {}


def _ratio(value: Any, default: float = 0.0) -> float:
    number = _float(value, default)
    return max(0.0, min(1.0, float(number or 0.0)))


def _float(value: Any, default: Any = None) -> Any:
    if value is None or value == "":
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if number == number and number not in {float("inf"), float("-inf")} else default


def _nullable_float(value: Any) -> float | None:
    return _float(value, None)


def _nullable_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
