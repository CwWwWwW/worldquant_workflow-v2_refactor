from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v) for v in value]
    if isinstance(value, tuple):
        return [str(v) for v in value]
    return []


@dataclass
class GovernanceDecision:
    allowed: bool = False
    reason: str = ""
    task_name: str = ""
    decision_type: str = ""
    model_version: str | None = None
    lifecycle_status: str | None = None
    model_weight: float = 0.0
    fallback_required: bool = True
    warnings: list[str] = field(default_factory=list)
    raw_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": bool(self.allowed),
            "reason": self.reason,
            "task_name": self.task_name,
            "decision_type": self.decision_type,
            "model_version": self.model_version,
            "lifecycle_status": self.lifecycle_status,
            "model_weight": float(self.model_weight or 0.0),
            "fallback_required": bool(self.fallback_required),
            "warnings": list(self.warnings),
            "raw_payload": dict(self.raw_payload),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "GovernanceDecision":
        data = _dict(data)
        return cls(
            allowed=bool(data.get("allowed", False)),
            reason=str(data.get("reason", "")),
            task_name=str(data.get("task_name", "")),
            decision_type=str(data.get("decision_type", "")),
            model_version=data.get("model_version"),
            lifecycle_status=data.get("lifecycle_status"),
            model_weight=float(data.get("model_weight", 0.0) or 0.0),
            fallback_required=bool(data.get("fallback_required", True)),
            warnings=_list(data.get("warnings")),
            raw_payload=_dict(data.get("raw_payload")),
        )


@dataclass
class GovernanceAction:
    action: str = ""
    task_name: str = ""
    model_version: str | None = None
    reason: str = ""
    raw_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"action": self.action, "task_name": self.task_name, "model_version": self.model_version, "reason": self.reason, "raw_payload": dict(self.raw_payload)}

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "GovernanceAction":
        data = _dict(data)
        return cls(action=str(data.get("action", "")), task_name=str(data.get("task_name", "")), model_version=data.get("model_version"), reason=str(data.get("reason", "")), raw_payload=_dict(data.get("raw_payload")))


@dataclass
class GovernanceCheckResult:
    ok: bool = True
    task_name: str = ""
    recommended_action: str = "keep_shadow"
    reason: str = ""
    warnings: list[str] = field(default_factory=list)
    raw_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"ok": bool(self.ok), "task_name": self.task_name, "recommended_action": self.recommended_action, "reason": self.reason, "warnings": list(self.warnings), "raw_payload": dict(self.raw_payload)}

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "GovernanceCheckResult":
        data = _dict(data)
        return cls(ok=bool(data.get("ok", True)), task_name=str(data.get("task_name", "")), recommended_action=str(data.get("recommended_action", "keep_shadow")), reason=str(data.get("reason", "")), warnings=_list(data.get("warnings")), raw_payload=_dict(data.get("raw_payload")))


@dataclass
class TaskGovernanceState:
    task_name: str = ""
    active_model_version: str | None = None
    lifecycle_status: str = "shadow"
    model_weight: float = 0.0
    fallback_active: bool = True
    last_online_eval: dict[str, Any] = field(default_factory=dict)
    last_event: dict[str, Any] = field(default_factory=dict)
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_name": self.task_name,
            "active_model_version": self.active_model_version,
            "lifecycle_status": self.lifecycle_status,
            "model_weight": float(self.model_weight or 0.0),
            "fallback_active": bool(self.fallback_active),
            "last_online_eval": dict(self.last_online_eval),
            "last_event": dict(self.last_event),
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "TaskGovernanceState":
        data = _dict(data)
        return cls(
            task_name=str(data.get("task_name", "")),
            active_model_version=data.get("active_model_version"),
            lifecycle_status=str(data.get("lifecycle_status", "shadow")),
            model_weight=float(data.get("model_weight", 0.0) or 0.0),
            fallback_active=bool(data.get("fallback_active", True)),
            last_online_eval=_dict(data.get("last_online_eval")),
            last_event=_dict(data.get("last_event")),
            updated_at=str(data.get("updated_at", "")),
        )
