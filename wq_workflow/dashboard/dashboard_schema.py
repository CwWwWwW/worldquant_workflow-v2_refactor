from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    try:
        return str(value)
    except Exception:
        return repr(value)


@dataclass
class DashboardSourceStatus:
    source: str
    available: bool = False
    stale: bool = False
    path: str | None = None
    updated_at: str | None = None
    warning_count: int = 0
    summary: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _json_safe(asdict(self))


@dataclass
class DashboardRuntimeStatus:
    generated_at: str = ""
    workflow_running: bool | None = None
    current_phase: str | None = None
    current_template: str | None = None
    current_alpha_id: str | None = None
    current_iteration: int | None = None
    current_state: str | None = None
    platform_waiting: bool | None = None
    parse_waiting: bool | None = None
    sc_check_status: str | None = None
    last_event_at: str | None = None
    recent_events: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _json_safe(asdict(self))


@dataclass
class DashboardMLStatus:
    model_enabled: bool | None = None
    active_model_id: str | None = None
    model_count: int | None = None
    training_sample_count: int | None = None
    prediction_count: int | None = None
    last_prediction_at: str | None = None
    safety_gate_status: str | None = None
    ml_parameters: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _json_safe(asdict(self))


@dataclass
class DashboardStrategyStatus:
    champion: str | None = None
    challenger_count: int | None = None
    limited_active_count: int | None = None
    shadow_count: int | None = None
    disabled_count: int | None = None
    budget_allocations: list[dict[str, Any]] = field(default_factory=list)
    budget_total_ratio: float | None = None
    high_risk_count: int | None = None
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _json_safe(asdict(self))


@dataclass
class DashboardObservabilityStatus:
    metrics_available: bool = False
    alerts_available: bool = False
    diagnosis_available: bool = False
    explainability_available: bool = False
    overall_health: str | None = None
    alert_count: int = 0
    critical_count: int = 0
    warning_count: int = 0
    key_findings: list[str] = field(default_factory=list)
    recommended_human_checks: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _json_safe(asdict(self))


@dataclass
class DashboardSnapshot:
    generated_at: str
    runtime: DashboardRuntimeStatus = field(default_factory=DashboardRuntimeStatus)
    ml: DashboardMLStatus = field(default_factory=DashboardMLStatus)
    strategy: DashboardStrategyStatus = field(default_factory=DashboardStrategyStatus)
    observability: DashboardObservabilityStatus = field(default_factory=DashboardObservabilityStatus)
    sources: list[DashboardSourceStatus] = field(default_factory=list)
    global_warnings: list[str] = field(default_factory=list)
    raw_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _json_safe(asdict(self))
