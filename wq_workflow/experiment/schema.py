from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from datetime import UTC, datetime
from typing import Any, TypeVar

from wq_workflow.data.json_utils import to_jsonable


VALID_VARIABLE_TYPES = {
    "template_family",
    "operator_family",
    "mutation_type",
    "field_family",
    "behavior_family",
    "strategy",
    "legacy_baseline",
    "other",
}

VALID_ARM_ROLES = {"control", "treatment", "baseline", "exploratory"}
VALID_PLAN_STATUSES = {"planned", "active", "paused", "completed", "archived"}
VALID_ASSIGNED_BY = {"default_planner", "legacy_adapter", "manual", "unknown"}


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _clean_dict(value: Any) -> dict[str, Any]:
    cleaned = to_jsonable(value if isinstance(value, dict) else {})
    return cleaned if isinstance(cleaned, dict) else {}


def _clean_value(value: Any) -> Any:
    return to_jsonable(value)


T = TypeVar("T")


def _coerce_dataclass(cls: type[T], data: Any) -> T:
    source = data if isinstance(data, dict) else {}
    names = {item.name for item in fields(cls)}
    kwargs = {name: source.get(name) for name in names if name in source}
    return cls(**kwargs)  # type: ignore[arg-type]


@dataclass
class ExperimentHypothesis:
    hypothesis_id: str
    name: str
    description: str
    variable_type: str
    variable_value: str
    expected_effect: str
    created_at: str = field(default_factory=utc_now_iso)
    raw_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["raw_payload"] = _clean_dict(self.raw_payload)
        return _clean_dict(data)

    @classmethod
    def from_dict(cls, data: Any) -> "ExperimentHypothesis":
        source = data if isinstance(data, dict) else {}
        return cls(
            hypothesis_id=str(source.get("hypothesis_id") or ""),
            name=str(source.get("name") or ""),
            description=str(source.get("description") or ""),
            variable_type=str(source.get("variable_type") or "other"),
            variable_value=str(source.get("variable_value") or ""),
            expected_effect=str(source.get("expected_effect") or ""),
            created_at=str(source.get("created_at") or utc_now_iso()),
            raw_payload=_clean_dict(source.get("raw_payload") or {}),
        )


@dataclass
class ExperimentArm:
    arm_id: str
    experiment_id: str
    name: str
    role: str
    variable_type: str
    variable_value: str
    allocation_hint: float = 0.0
    is_control: bool = False
    raw_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["allocation_hint"] = float(self.allocation_hint or 0.0)
        data["is_control"] = bool(self.is_control)
        data["raw_payload"] = _clean_dict(self.raw_payload)
        return _clean_dict(data)

    @classmethod
    def from_dict(cls, data: Any) -> "ExperimentArm":
        source = data if isinstance(data, dict) else {}
        try:
            allocation_hint = float(source.get("allocation_hint") or 0.0)
        except (TypeError, ValueError):
            allocation_hint = 0.0
        return cls(
            arm_id=str(source.get("arm_id") or ""),
            experiment_id=str(source.get("experiment_id") or ""),
            name=str(source.get("name") or ""),
            role=str(source.get("role") or "treatment"),
            variable_type=str(source.get("variable_type") or "other"),
            variable_value=str(source.get("variable_value") or ""),
            allocation_hint=allocation_hint,
            is_control=bool(source.get("is_control", False)),
            raw_payload=_clean_dict(source.get("raw_payload") or {}),
        )


@dataclass
class ExperimentPlan:
    experiment_id: str
    name: str
    status: str
    hypothesis: ExperimentHypothesis
    arms: list[ExperimentArm]
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    raw_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _clean_dict(
            {
                "experiment_id": self.experiment_id,
                "name": self.name,
                "status": self.status,
                "hypothesis": self.hypothesis.to_dict(),
                "arms": [arm.to_dict() for arm in self.arms],
                "created_at": self.created_at,
                "updated_at": self.updated_at,
                "raw_payload": _clean_dict(self.raw_payload),
            }
        )

    @classmethod
    def from_dict(cls, data: Any) -> "ExperimentPlan":
        source = data if isinstance(data, dict) else {}
        hypothesis = source.get("hypothesis")
        if isinstance(hypothesis, ExperimentHypothesis):
            hypothesis_obj = hypothesis
        else:
            hypothesis_obj = ExperimentHypothesis.from_dict(hypothesis or {})
        arms: list[ExperimentArm] = []
        for item in source.get("arms") or []:
            arms.append(item if isinstance(item, ExperimentArm) else ExperimentArm.from_dict(item))
        return cls(
            experiment_id=str(source.get("experiment_id") or ""),
            name=str(source.get("name") or ""),
            status=str(source.get("status") or "planned"),
            hypothesis=hypothesis_obj,
            arms=arms,
            created_at=str(source.get("created_at") or utc_now_iso()),
            updated_at=str(source.get("updated_at") or utc_now_iso()),
            raw_payload=_clean_dict(source.get("raw_payload") or {}),
        )


@dataclass
class ExperimentAssignment:
    assignment_id: str
    experiment_id: str
    arm_id: str
    alpha_id: str | None = None
    expression_hash: str | None = None
    template_name: str | None = None
    template_family: str | None = None
    operator_family: str | None = None
    mutation_type: str | None = None
    field_family: str | None = None
    behavior_family: str | None = None
    assigned_by: str = "default_planner"
    created_at: str = field(default_factory=utc_now_iso)
    raw_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["raw_payload"] = _clean_dict(self.raw_payload)
        return _clean_dict(data)

    @classmethod
    def from_dict(cls, data: Any) -> "ExperimentAssignment":
        source = data if isinstance(data, dict) else {}
        return cls(
            assignment_id=str(source.get("assignment_id") or ""),
            experiment_id=str(source.get("experiment_id") or ""),
            arm_id=str(source.get("arm_id") or ""),
            alpha_id=_nullable_str(source.get("alpha_id")),
            expression_hash=_nullable_str(source.get("expression_hash")),
            template_name=_nullable_str(source.get("template_name")),
            template_family=_nullable_str(source.get("template_family")),
            operator_family=_nullable_str(source.get("operator_family")),
            mutation_type=_nullable_str(source.get("mutation_type")),
            field_family=_nullable_str(source.get("field_family")),
            behavior_family=_nullable_str(source.get("behavior_family")),
            assigned_by=str(source.get("assigned_by") or "unknown"),
            created_at=str(source.get("created_at") or utc_now_iso()),
            raw_payload=_clean_dict(source.get("raw_payload") or {}),
        )


@dataclass
class ExperimentResult:
    result_id: str
    assignment_id: str
    experiment_id: str
    arm_id: str
    alpha_id: str | None = None
    success: bool | None = None
    reward: float | None = None
    sharpe: float | None = None
    fitness: float | None = None
    returns: float | None = None
    turnover: float | None = None
    drawdown: float | None = None
    margin: float | None = None
    platform_sc_status: str | None = None
    platform_sc_abs_max: float | None = None
    quality_passed: bool | None = None
    failure_type: str | None = None
    created_at: str = field(default_factory=utc_now_iso)
    raw_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["raw_payload"] = _clean_dict(self.raw_payload)
        return _clean_dict(data)

    @classmethod
    def from_dict(cls, data: Any) -> "ExperimentResult":
        source = data if isinstance(data, dict) else {}
        return cls(
            result_id=str(source.get("result_id") or ""),
            assignment_id=str(source.get("assignment_id") or ""),
            experiment_id=str(source.get("experiment_id") or ""),
            arm_id=str(source.get("arm_id") or ""),
            alpha_id=_nullable_str(source.get("alpha_id")),
            success=_nullable_bool(source.get("success")),
            reward=_nullable_float(source.get("reward")),
            sharpe=_nullable_float(source.get("sharpe")),
            fitness=_nullable_float(source.get("fitness")),
            returns=_nullable_float(source.get("returns")),
            turnover=_nullable_float(source.get("turnover")),
            drawdown=_nullable_float(source.get("drawdown")),
            margin=_nullable_float(source.get("margin")),
            platform_sc_status=_nullable_str(source.get("platform_sc_status")),
            platform_sc_abs_max=_nullable_float(source.get("platform_sc_abs_max")),
            quality_passed=_nullable_bool(source.get("quality_passed")),
            failure_type=_nullable_str(source.get("failure_type")),
            created_at=str(source.get("created_at") or utc_now_iso()),
            raw_payload=_clean_dict(source.get("raw_payload") or {}),
        )


@dataclass
class ExperimentSummary:
    experiment_id: str
    arm_id: str
    sample_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    avg_reward: float | None = None
    avg_sharpe: float | None = None
    avg_fitness: float | None = None
    avg_platform_sc_abs_max: float | None = None
    quality_pass_rate: float | None = None
    updated_at: str = field(default_factory=utc_now_iso)
    raw_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["raw_payload"] = _clean_dict(self.raw_payload)
        return _clean_dict(data)

    @classmethod
    def from_dict(cls, data: Any) -> "ExperimentSummary":
        source = data if isinstance(data, dict) else {}
        return cls(
            experiment_id=str(source.get("experiment_id") or ""),
            arm_id=str(source.get("arm_id") or ""),
            sample_count=_int(source.get("sample_count"), 0),
            success_count=_int(source.get("success_count"), 0),
            failure_count=_int(source.get("failure_count"), 0),
            avg_reward=_nullable_float(source.get("avg_reward")),
            avg_sharpe=_nullable_float(source.get("avg_sharpe")),
            avg_fitness=_nullable_float(source.get("avg_fitness")),
            avg_platform_sc_abs_max=_nullable_float(source.get("avg_platform_sc_abs_max")),
            quality_pass_rate=_nullable_float(source.get("quality_pass_rate")),
            updated_at=str(source.get("updated_at") or utc_now_iso()),
            raw_payload=_clean_dict(source.get("raw_payload") or {}),
        )


def _nullable_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text != "" else None


def _nullable_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number in {float("inf"), float("-inf")}:
        return None
    return number


def _nullable_bool(value: Any) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on", "passed", "success"}:
        return True
    if text in {"0", "false", "no", "n", "off", "failed", "fail"}:
        return False
    return None


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
