from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any


class ModelLifecycleStatus(str, Enum):
    CANDIDATE = "candidate"
    SHADOW = "shadow"
    CHALLENGER = "challenger"
    LIMITED_ACTIVE = "limited_active"
    CHAMPION = "champion"
    DEGRADED = "degraded"
    DISABLED = "disabled"
    ROLLED_BACK = "rolled_back"
    EXPIRED = "expired"


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def expires_at_iso(days: int | float = 14) -> str:
    return (datetime.now(UTC) + timedelta(days=float(days or 0))).isoformat(timespec="seconds")


def _status(value: str | ModelLifecycleStatus | None) -> str:
    if isinstance(value, ModelLifecycleStatus):
        return value.value
    return str(value or ModelLifecycleStatus.SHADOW.value)


def is_terminal_status(status: str | ModelLifecycleStatus | None) -> bool:
    return _status(status) in {ModelLifecycleStatus.DISABLED.value, ModelLifecycleStatus.ROLLED_BACK.value, ModelLifecycleStatus.EXPIRED.value}


def default_weight_for_status(status: str | ModelLifecycleStatus | None) -> float:
    status_value = _status(status)
    return {
        ModelLifecycleStatus.CANDIDATE.value: 0.0,
        ModelLifecycleStatus.SHADOW.value: 0.0,
        ModelLifecycleStatus.CHALLENGER.value: 0.05,
        ModelLifecycleStatus.LIMITED_ACTIVE.value: 0.25,
        ModelLifecycleStatus.CHAMPION.value: 1.0,
        ModelLifecycleStatus.DEGRADED.value: 0.05,
        ModelLifecycleStatus.DISABLED.value: 0.0,
        ModelLifecycleStatus.ROLLED_BACK.value: 0.0,
        ModelLifecycleStatus.EXPIRED.value: 0.0,
    }.get(status_value, 0.0)


def is_hard_decision_allowed_status(status: str | ModelLifecycleStatus | None) -> bool:
    return _status(status) in {ModelLifecycleStatus.LIMITED_ACTIVE.value, ModelLifecycleStatus.CHAMPION.value}


def can_transition(current: str | ModelLifecycleStatus | None, target: str | ModelLifecycleStatus | None) -> bool:
    current_value = _status(current)
    target_value = _status(target)
    valid = {s.value for s in ModelLifecycleStatus}
    if target_value not in valid or current_value not in valid:
        return False
    if current_value == target_value:
        return True
    if current_value == ModelLifecycleStatus.CANDIDATE.value and target_value == ModelLifecycleStatus.CHAMPION.value:
        return False
    if is_terminal_status(current_value) and not is_terminal_status(target_value):
        return False
    return True


def _parse_iso(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    except Exception:
        return None


def is_expired(expires_at: Any) -> bool:
    dt = _parse_iso(expires_at)
    return bool(dt and dt <= datetime.now(UTC))


@dataclass
class ModelLifecycleMetadata:
    lifecycle_status: str = ModelLifecycleStatus.SHADOW.value
    model_weight: float = 0.0
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    expires_at: str | None = None
    promotion_reason: str = ""
    disable_reason: str = ""
    rollback_reason: str = ""
    raw_payload: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.expires_at:
            self.expires_at = expires_at_iso(14)
        if self.model_weight is None:
            self.model_weight = default_weight_for_status(self.lifecycle_status)
        if is_terminal_status(self.lifecycle_status):
            self.model_weight = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "lifecycle_status": self.lifecycle_status,
            "model_weight": float(self.model_weight or 0.0),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "expires_at": self.expires_at,
            "promotion_reason": self.promotion_reason,
            "disable_reason": self.disable_reason,
            "rollback_reason": self.rollback_reason,
            "raw_payload": dict(self.raw_payload),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ModelLifecycleMetadata":
        data = dict(data) if isinstance(data, dict) else {}
        status = str(data.get("lifecycle_status") or data.get("status") or ModelLifecycleStatus.SHADOW.value)
        return cls(
            lifecycle_status=status,
            model_weight=float(data.get("model_weight", default_weight_for_status(status)) or 0.0),
            created_at=str(data.get("created_at") or utc_now_iso()),
            updated_at=str(data.get("updated_at") or utc_now_iso()),
            expires_at=data.get("expires_at"),
            promotion_reason=str(data.get("promotion_reason", "")),
            disable_reason=str(data.get("disable_reason", "")),
            rollback_reason=str(data.get("rollback_reason", "")),
            raw_payload=dict(data.get("raw_payload") or {}),
        )
