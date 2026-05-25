from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from wq_workflow.data.json_utils import safe_float, safe_int, to_jsonable

BUDGET_RULE_TYPES = {
    "baseline_floor",
    "exploration_floor",
    "disabled_zero",
    "governance_block_zero",
    "high_risk_cap",
    "high_sc_cap",
    "shadow_cap",
    "challenger_cap",
    "limited_active_cap",
    "champion_floor",
    "insufficient_evidence_cap",
    "normalization",
}
BUDGET_STATUSES = {"blocked", "hold", "observe", "test", "scale_limited", "baseline", "exploration"}


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _clean_dict(value: Any) -> dict[str, Any]:
    cleaned = to_jsonable(value if isinstance(value, dict) else {})
    return cleaned if isinstance(cleaned, dict) else {}


def _clean_list(value: Any) -> list[Any]:
    cleaned = to_jsonable(value if isinstance(value, list) else [])
    return cleaned if isinstance(cleaned, list) else []


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def _bool(value: Any, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on", "enabled"}


def _nullable_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(safe_float(value, 0.0) or 0.0)


def _nullable_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(safe_int(value, 0) or 0)


def _bounded(value: Any, default: float = 0.0) -> float:
    return max(0.0, min(1.0, float(safe_float(value, default) or 0.0)))


def _status(value: Any, default: str = "hold") -> str:
    text = _text(value or default, default).strip().lower()
    return text if text in BUDGET_STATUSES else default


def _rule_type(value: Any, default: str = "normalization") -> str:
    text = _text(value or default, default).strip().lower()
    return text if text in BUDGET_RULE_TYPES else default


@dataclass
class StrategyBudgetRule:
    rule_id: str = ""
    rule_type: str = "normalization"
    description: str = ""
    enabled: bool = True
    priority: int = 100
    min_ratio: float | None = None
    max_ratio: float | None = None
    applies_to_state: str | None = None
    applies_to_strategy_type: str | None = None
    reason_code: str = ""
    created_at: str = field(default_factory=utc_now_iso)
    raw_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["rule_type"] = _rule_type(self.rule_type)
        data["enabled"] = _bool(self.enabled, True)
        data["priority"] = int(safe_int(self.priority, 100) or 0)
        data["min_ratio"] = _nullable_float(self.min_ratio)
        data["max_ratio"] = _nullable_float(self.max_ratio)
        data["applies_to_state"] = None if self.applies_to_state in {None, ""} else str(self.applies_to_state)
        data["applies_to_strategy_type"] = None if self.applies_to_strategy_type in {None, ""} else str(self.applies_to_strategy_type)
        data["raw_payload"] = _clean_dict(self.raw_payload)
        return _clean_dict(data)

    @classmethod
    def from_dict(cls, data: Any) -> "StrategyBudgetRule":
        source = data.to_dict() if isinstance(data, StrategyBudgetRule) else (data if isinstance(data, dict) else {})
        return cls(
            rule_id=_text(source.get("rule_id") or source.get("id")),
            rule_type=_rule_type(source.get("rule_type")),
            description=_text(source.get("description")),
            enabled=_bool(source.get("enabled"), True),
            priority=int(safe_int(source.get("priority"), 100) or 0),
            min_ratio=_nullable_float(source.get("min_ratio")),
            max_ratio=_nullable_float(source.get("max_ratio")),
            applies_to_state=None if source.get("applies_to_state") in {None, ""} else str(source.get("applies_to_state")),
            applies_to_strategy_type=None if source.get("applies_to_strategy_type") in {None, ""} else str(source.get("applies_to_strategy_type")),
            reason_code=_text(source.get("reason_code")),
            created_at=_text(source.get("created_at") or utc_now_iso()),
            raw_payload=_clean_dict(source.get("raw_payload") or {}),
        )


@dataclass
class StrategyBudgetAllocation:
    allocation_id: str = ""
    plan_id: str = ""
    strategy_id: str = ""
    strategy_type: str = "manual_or_unknown"
    state: str = "shadow"
    role: str = "unknown"
    score: float = 0.0
    confidence: str = "insufficient"
    risk_level: str = "medium"
    requested_ratio: float = 0.0
    suggested_ratio: float = 0.0
    min_floor_ratio: float = 0.0
    hard_cap_ratio: float = 1.0
    suggested_slots: int | None = None
    budget_status: str = "hold"
    reason_codes: list[str] = field(default_factory=list)
    risk_flags: list[str] = field(default_factory=list)
    auto_apply_allowed: bool = False
    created_at: str = field(default_factory=utc_now_iso)
    raw_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for key in ("score", "requested_ratio", "suggested_ratio", "min_floor_ratio", "hard_cap_ratio"):
            data[key] = _bounded(data.get(key), 0.0 if key != "hard_cap_ratio" else 1.0)
        data["suggested_slots"] = _nullable_int(self.suggested_slots)
        data["budget_status"] = _status(self.budget_status)
        data["reason_codes"] = [str(item) for item in _clean_list(self.reason_codes)]
        data["risk_flags"] = [str(item) for item in _clean_list(self.risk_flags)]
        data["auto_apply_allowed"] = False
        data["raw_payload"] = _clean_dict(self.raw_payload)
        return _clean_dict(data)

    @classmethod
    def from_dict(cls, data: Any) -> "StrategyBudgetAllocation":
        source = data.to_dict() if isinstance(data, StrategyBudgetAllocation) else (data if isinstance(data, dict) else {})
        return cls(
            allocation_id=_text(source.get("allocation_id") or source.get("id")),
            plan_id=_text(source.get("plan_id")),
            strategy_id=_text(source.get("strategy_id")),
            strategy_type=_text(source.get("strategy_type") or "manual_or_unknown", "manual_or_unknown"),
            state=_text(source.get("state") or "shadow", "shadow"),
            role=_text(source.get("role") or "unknown", "unknown"),
            score=_bounded(source.get("score"), 0.0),
            confidence=_text(source.get("confidence") or "insufficient", "insufficient"),
            risk_level=_text(source.get("risk_level") or "medium", "medium"),
            requested_ratio=_bounded(source.get("requested_ratio"), 0.0),
            suggested_ratio=_bounded(source.get("suggested_ratio"), 0.0),
            min_floor_ratio=_bounded(source.get("min_floor_ratio"), 0.0),
            hard_cap_ratio=_bounded(source.get("hard_cap_ratio"), 1.0),
            suggested_slots=_nullable_int(source.get("suggested_slots")),
            budget_status=_status(source.get("budget_status")),
            reason_codes=[str(item) for item in _clean_list(source.get("reason_codes") or [])],
            risk_flags=[str(item) for item in _clean_list(source.get("risk_flags") or [])],
            auto_apply_allowed=False,
            created_at=_text(source.get("created_at") or utc_now_iso()),
            raw_payload=_clean_dict(source.get("raw_payload") or {}),
        )


@dataclass
class StrategyBudgetPlan:
    plan_id: str = ""
    generated_at: str = field(default_factory=utc_now_iso)
    mode: str = "advisory"
    total_budget_hint: int | None = None
    allocations: list[StrategyBudgetAllocation] = field(default_factory=list)
    total_suggested_ratio: float = 0.0
    warnings: list[str] = field(default_factory=list)
    raw_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["mode"] = str(self.mode or "advisory")
        data["total_budget_hint"] = _nullable_int(self.total_budget_hint)
        data["allocations"] = [StrategyBudgetAllocation.from_dict(item).to_dict() for item in self.allocations]
        data["total_suggested_ratio"] = float(safe_float(self.total_suggested_ratio, 0.0) or 0.0)
        data["warnings"] = [str(item) for item in _clean_list(self.warnings)]
        data["raw_payload"] = _clean_dict(self.raw_payload)
        return _clean_dict(data)

    @classmethod
    def from_dict(cls, data: Any) -> "StrategyBudgetPlan":
        source = data.to_dict() if isinstance(data, StrategyBudgetPlan) else (data if isinstance(data, dict) else {})
        return cls(
            plan_id=_text(source.get("plan_id") or source.get("id")),
            generated_at=_text(source.get("generated_at") or utc_now_iso()),
            mode=_text(source.get("mode") or "advisory", "advisory"),
            total_budget_hint=_nullable_int(source.get("total_budget_hint")),
            allocations=[StrategyBudgetAllocation.from_dict(item) for item in _clean_list(source.get("allocations") or [])],
            total_suggested_ratio=float(safe_float(source.get("total_suggested_ratio"), 0.0) or 0.0),
            warnings=[str(item) for item in _clean_list(source.get("warnings") or [])],
            raw_payload=_clean_dict(source.get("raw_payload") or {}),
        )


@dataclass
class StrategyBudgetReport:
    report_id: str = ""
    generated_at: str = field(default_factory=utc_now_iso)
    mode: str = "advisory"
    total_budget_hint: int | None = None
    allocations: list[StrategyBudgetAllocation] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    raw_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["mode"] = str(self.mode or "advisory")
        data["total_budget_hint"] = _nullable_int(self.total_budget_hint)
        data["allocations"] = [StrategyBudgetAllocation.from_dict(item).to_dict() for item in self.allocations]
        data["warnings"] = [str(item) for item in _clean_list(self.warnings)]
        data["raw_payload"] = _clean_dict(self.raw_payload)
        return _clean_dict(data)

    @classmethod
    def from_dict(cls, data: Any) -> "StrategyBudgetReport":
        source = data.to_dict() if isinstance(data, StrategyBudgetReport) else (data if isinstance(data, dict) else {})
        return cls(
            report_id=_text(source.get("report_id") or source.get("id")),
            generated_at=_text(source.get("generated_at") or utc_now_iso()),
            mode=_text(source.get("mode") or "advisory", "advisory"),
            total_budget_hint=_nullable_int(source.get("total_budget_hint")),
            allocations=[StrategyBudgetAllocation.from_dict(item) for item in _clean_list(source.get("allocations") or [])],
            warnings=[str(item) for item in _clean_list(source.get("warnings") or [])],
            raw_payload=_clean_dict(source.get("raw_payload") or {}),
        )
