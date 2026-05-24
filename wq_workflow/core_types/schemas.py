from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields, is_dataclass
from datetime import datetime
from typing import Any, Generic, TypeVar

T = TypeVar("T")


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _filter(cls: type, payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    allowed = {f.name for f in fields(cls)}
    return {k: v for k, v in payload.items() if k in allowed}


class DictCompatMixin:
    def to_dict(self) -> dict[str, Any]:
        if is_dataclass(self):
            return asdict(self)
        return dict(getattr(self, "__dict__", {}))

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None):
        return cls(**_filter(cls, payload))


@dataclass
class CandidateDraft(DictCompatMixin):
    alpha_id: str = ""
    expression: str = ""
    parent_id: str = ""
    source: str = ""
    template_name: str = ""
    mutation_type: str = ""
    generation_metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_now)


@dataclass
class SimulationResult(DictCompatMixin):
    alpha_id: str = ""
    simulation_id: str = ""
    ok: bool = False
    metrics: dict[str, Any] = field(default_factory=dict)
    testing_status: str = ""
    result_fingerprint: str = ""
    freshness_score: float | None = None
    raw_payload: dict[str, Any] = field(default_factory=dict)
    error: str = ""


@dataclass
class PlatformSCResult(DictCompatMixin):
    status: str = ""
    max: float | None = None
    min: float | None = None
    abs_max: float | None = None
    selector: str = ""
    elapsed: float | None = None
    text_hash: str = ""
    raw_text_preview: str = ""
    error: str = ""

    def to_metrics(self) -> dict[str, Any]:
        if self.status != "complete":
            return {}
        return {
            "platform_sc_max": self.max,
            "platform_sc_min": self.min,
            "platform_sc_abs_max": self.abs_max,
        }

    def to_payload(self) -> dict[str, Any]:
        return self.to_dict()


@dataclass
class QualityResult(DictCompatMixin):
    passed: bool = False
    reason: str = ""
    warnings: list[str] = field(default_factory=list)
    testing_status: str = ""
    fail_count: int = 0
    pending_count: int = 0
    pass_count: int = 0
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class RewardResult(DictCompatMixin):
    reward: float = 0.0
    reward_components: dict[str, Any] = field(default_factory=dict)
    reward_version: str = "legacy"
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class PersistResult(DictCompatMixin):
    ok: bool = False
    candidate_saved: bool = False
    sqlite_saved: bool = False
    csv_saved: bool = False
    logs_saved: bool = False
    errors: list[str] = field(default_factory=list)


@dataclass
class DecisionSnapshot(DictCompatMixin):
    decision_id: str = ""
    decision_type: str = ""
    context: dict[str, Any] = field(default_factory=dict)
    available_actions: list[dict[str, Any]] = field(default_factory=list)
    chosen_action: dict[str, Any] = field(default_factory=dict)
    scores: dict[str, Any] = field(default_factory=dict)
    source: str = ""
    model_version: str = ""
    reason: str = ""
    created_at: str = field(default_factory=_now)


@dataclass
class ServiceResult(DictCompatMixin, Generic[T]):
    ok: bool = True
    data: T | None = None
    error: str = ""
    warnings: list[str] = field(default_factory=list)
    source: str = ""
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowError(DictCompatMixin):
    code: str = ""
    message: str = ""
    severity: str = "recoverable_error"
    source: str = ""
    recoverable: bool = True
    raw_payload: dict[str, Any] = field(default_factory=dict)
