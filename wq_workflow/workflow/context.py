from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class WorkflowContext:
    iteration_id: str
    alpha_id: str | None = None
    parent: dict[str, Any] | None = None
    candidate: dict[str, Any] | None = None
    strategy: dict[str, Any] | None = None
    experiment: dict[str, Any] | None = None
    alpha_representation: Any = None
    local_checks: dict[str, Any] = field(default_factory=dict)
    platform_result: dict[str, Any] = field(default_factory=dict)
    platform_sc: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
    reward: float | None = None
    quality: dict[str, Any] = field(default_factory=dict)
    decisions: list[dict[str, Any]] = field(default_factory=list)
    prediction_audits: list[dict[str, Any]] = field(default_factory=list)
    parent_decision_id: str | None = None
    policy_decision_id: str | None = None
    simulator_prediction: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
