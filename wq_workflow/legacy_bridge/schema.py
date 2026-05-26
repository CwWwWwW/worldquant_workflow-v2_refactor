from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from typing import Any

from .utils import json_safe, make_id, summarize_payload, truncate_text, utc_now_iso


def _str_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, tuple):
        return [str(item) for item in value]
    if value in (None, ""):
        return []
    return [str(value)]


def _dict(value: Any) -> dict[str, Any]:
    cleaned = json_safe(value if isinstance(value, dict) else {})
    return cleaned if isinstance(cleaned, dict) else {}


def _coerce_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


def _coerce_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except Exception:
        return None


@dataclass
class RuntimeStateSnapshot:
    snapshot_id: str = field(default_factory=lambda: make_id("runtime_state"))
    updated_at: str = field(default_factory=utc_now_iso)
    workflow_running: bool | None = None
    current_phase: str | None = None
    current_state: str | None = None
    current_template: str | None = None
    current_template_family: str | None = None
    current_operator: str | None = None
    current_alpha_id: str | None = None
    current_iteration: int | None = None
    current_run_id: str | None = None
    platform_waiting: bool | None = None
    platform_progress: float | None = None
    parse_waiting: bool | None = None
    parse_status: str | None = None
    sc_check_status: str | None = None
    last_sc_value: float | None = None
    last_result_status: str | None = None
    last_reward: float | None = None
    last_event_at: str | None = None
    last_error_summary: str | None = None
    ml_summary: dict[str, Any] = field(default_factory=dict)
    governance_summary: dict[str, Any] = field(default_factory=dict)
    strategy_summary: dict[str, Any] = field(default_factory=dict)
    observability_summary: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    raw_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return json_safe(asdict(self))

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "RuntimeStateSnapshot":
        data = payload if isinstance(payload, dict) else {}
        names = {field.name for field in fields(cls)}
        kwargs = {name: data.get(name) for name in names if name in data}
        for key in ("current_iteration",):
            if key in kwargs:
                kwargs[key] = _coerce_int(kwargs.get(key))
        for key in ("platform_progress", "last_sc_value", "last_reward"):
            if key in kwargs:
                kwargs[key] = _coerce_float(kwargs.get(key))
        for key in ("ml_summary", "governance_summary", "strategy_summary", "observability_summary", "raw_payload"):
            kwargs[key] = _dict(kwargs.get(key))
        kwargs["warnings"] = _str_list(kwargs.get("warnings"))
        return cls(**kwargs)


@dataclass
class RuntimeEvent:
    event_id: str = field(default_factory=lambda: make_id("runtime_event"))
    timestamp: str = field(default_factory=utc_now_iso)
    event_type: str = "UNKNOWN"
    state: str | None = None
    alpha_id: str | None = None
    iteration: int | None = None
    template_name: str | None = None
    template_family: str | None = None
    message: str = ""
    severity: str = "info"
    source: str = "legacy_iteration_observer"
    reason_codes: list[str] = field(default_factory=list)
    payload_summary: dict[str, Any] = field(default_factory=dict)
    raw_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["message"] = truncate_text(data.get("message"), 300)
        data["payload_summary"] = summarize_payload(data.get("payload_summary"), max_payload_chars=1000)
        data["raw_payload"] = summarize_payload(data.get("raw_payload"), max_payload_chars=1000)
        return json_safe(data)

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "RuntimeEvent":
        data = payload if isinstance(payload, dict) else {}
        names = {field.name for field in fields(cls)}
        kwargs = {name: data.get(name) for name in names if name in data}
        kwargs["iteration"] = _coerce_int(kwargs.get("iteration"))
        kwargs["reason_codes"] = _str_list(kwargs.get("reason_codes"))
        kwargs["payload_summary"] = _dict(kwargs.get("payload_summary"))
        kwargs["raw_payload"] = _dict(kwargs.get("raw_payload"))
        kwargs["message"] = truncate_text(kwargs.get("message"), 300)
        return cls(**kwargs)


@dataclass
class LegacyLearningEvidence:
    evidence_id: str = field(default_factory=lambda: make_id("legacy_evidence"))
    timestamp: str = field(default_factory=utc_now_iso)
    evidence_type: str = "unknown"
    source: str = "legacy_iteration_observer"
    alpha_id: str | None = None
    iteration: int | None = None
    template_name: str | None = None
    template_family: str | None = None
    operator: str | None = None
    observed: bool = True
    estimated: bool = False
    advisory: bool = False
    result_status: str | None = None
    reward: float | None = None
    sc_value: float | None = None
    sharpe: float | None = None
    fitness: float | None = None
    turnover: float | None = None
    failure_reason: str | None = None
    summary: str = ""
    reason_codes: list[str] = field(default_factory=list)
    raw_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["summary"] = truncate_text(data.get("summary"), 300)
        data["failure_reason"] = truncate_text(data.get("failure_reason"), 300) if data.get("failure_reason") else None
        data["raw_payload"] = summarize_payload(data.get("raw_payload"), max_payload_chars=1000)
        return json_safe(data)

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "LegacyLearningEvidence":
        data = payload if isinstance(payload, dict) else {}
        names = {field.name for field in fields(cls)}
        kwargs = {name: data.get(name) for name in names if name in data}
        kwargs["iteration"] = _coerce_int(kwargs.get("iteration"))
        for key in ("reward", "sc_value", "sharpe", "fitness", "turnover"):
            kwargs[key] = _coerce_float(kwargs.get(key))
        kwargs["reason_codes"] = _str_list(kwargs.get("reason_codes"))
        kwargs["raw_payload"] = _dict(kwargs.get("raw_payload"))
        kwargs["summary"] = truncate_text(kwargs.get("summary"), 300)
        return cls(**kwargs)
