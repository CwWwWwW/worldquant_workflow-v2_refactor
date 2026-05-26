from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .utils import clean_dict, clean_list, json_safe, safe_float_value, safe_int_value, utc_now_iso


RULE_TYPES = {
    "absolute_threshold",
    "relative_change",
    "moving_average_shift",
    "missing_metric",
    "stale_source",
    "spike",
    "drop",
    "ratio_out_of_range",
}
DIRECTIONS = {"increase", "decrease", "both"}
SEVERITIES = {"info", "warning", "critical"}
CONDITION_TYPES = {
    "drift_signal_triggered",
    "source_unavailable",
    "source_stale",
    "warning_count_high",
    "missing_status_file",
    "platform_failure_spike",
    "parse_failure_spike",
    "sc_risk_high",
    "model_failure_spike",
    "governance_block_spike",
    "strategy_budget_concentration",
    "database_unavailable",
    "disk_low",
}
ALERT_STATUSES = {"open", "acknowledged", "closed", "suppressed"}
AREAS = {
    "workflow",
    "platform",
    "parsing",
    "sc_risk",
    "ml",
    "governance",
    "experiment",
    "offline_replay",
    "counterfactual",
    "strategy",
    "strategy_budget",
    "database",
    "system",
    "overall",
}
DIAGNOSIS_STATUSES = {"healthy", "watch", "degraded", "critical", "unknown"}


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def _choice(value: Any, allowed: set[str], default: str) -> str:
    text = _text(value or default, default).strip()
    return text if text in allowed else default


def _bool(value: Any, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on", "enabled"}


def _value(value: Any) -> int | float | str | bool | None:
    cleaned = json_safe(value)
    if isinstance(cleaned, (int, float, str, bool)) or cleaned is None:
        return cleaned
    return str(cleaned)


@dataclass
class DriftRule:
    rule_id: str = ""
    metric_name: str = ""
    source: str | None = None
    rule_type: str = "relative_change"
    window_size: int = 20
    baseline_window_size: int = 100
    threshold: float = 0.0
    direction: str = "both"
    severity: str = "warning"
    enabled: bool = True
    description: str = ""
    created_at: str = field(default_factory=utc_now_iso)
    raw_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["rule_id"] = _text(self.rule_id or f"drift_rule:{self.metric_name}:{self.rule_type}")
        data["metric_name"] = _text(self.metric_name)
        data["source"] = None if self.source in {None, ""} else str(self.source)
        data["rule_type"] = _choice(self.rule_type, RULE_TYPES, "relative_change")
        data["window_size"] = max(1, safe_int_value(self.window_size, 20))
        data["baseline_window_size"] = max(1, safe_int_value(self.baseline_window_size, 100))
        data["threshold"] = safe_float_value(self.threshold, 0.0)
        data["direction"] = _choice(self.direction, DIRECTIONS, "both")
        data["severity"] = _choice(self.severity, SEVERITIES, "warning")
        data["enabled"] = _bool(self.enabled, True)
        data["description"] = _text(self.description)
        data["created_at"] = _text(self.created_at or utc_now_iso())
        data["raw_payload"] = clean_dict(self.raw_payload)
        return clean_dict(data)

    @classmethod
    def from_dict(cls, data: Any) -> "DriftRule":
        source = data.to_dict() if isinstance(data, DriftRule) else (data if isinstance(data, dict) else {})
        return cls(
            rule_id=_text(source.get("rule_id") or source.get("id")),
            metric_name=_text(source.get("metric_name") or source.get("name")),
            source=None if source.get("source") in {None, ""} else str(source.get("source")),
            rule_type=_choice(source.get("rule_type"), RULE_TYPES, "relative_change"),
            window_size=max(1, safe_int_value(source.get("window_size"), 20)),
            baseline_window_size=max(1, safe_int_value(source.get("baseline_window_size"), 100)),
            threshold=safe_float_value(source.get("threshold"), 0.0),
            direction=_choice(source.get("direction"), DIRECTIONS, "both"),
            severity=_choice(source.get("severity"), SEVERITIES, "warning"),
            enabled=_bool(source.get("enabled"), True),
            description=_text(source.get("description")),
            created_at=_text(source.get("created_at") or utc_now_iso()),
            raw_payload=clean_dict(source.get("raw_payload") or {}),
        )


@dataclass
class DriftSignal:
    signal_id: str = ""
    rule_id: str = ""
    source: str = "unknown"
    metric_name: str = ""
    current_value: int | float | str | bool | None = None
    baseline_value: int | float | str | bool | None = None
    delta: float | None = None
    delta_ratio: float | None = None
    threshold: float | None = None
    triggered: bool = False
    severity: str = "warning"
    reason_codes: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now_iso)
    raw_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["signal_id"] = _text(self.signal_id or f"drift_signal:{self.rule_id}:{self.metric_name}:{self.created_at}")
        data["rule_id"] = _text(self.rule_id)
        data["source"] = _text(self.source or "unknown", "unknown")
        data["metric_name"] = _text(self.metric_name)
        data["current_value"] = _value(self.current_value)
        data["baseline_value"] = _value(self.baseline_value)
        data["delta"] = None if self.delta is None else safe_float_value(self.delta, 0.0)
        data["delta_ratio"] = None if self.delta_ratio is None else safe_float_value(self.delta_ratio, 0.0)
        data["threshold"] = None if self.threshold is None else safe_float_value(self.threshold, 0.0)
        data["triggered"] = _bool(self.triggered)
        data["severity"] = _choice(self.severity, SEVERITIES, "warning")
        data["reason_codes"] = [str(item) for item in clean_list(self.reason_codes)]
        data["created_at"] = _text(self.created_at or utc_now_iso())
        data["raw_payload"] = clean_dict(self.raw_payload)
        return clean_dict(data)

    @classmethod
    def from_dict(cls, data: Any) -> "DriftSignal":
        source = data.to_dict() if isinstance(data, DriftSignal) else (data if isinstance(data, dict) else {})
        return cls(
            signal_id=_text(source.get("signal_id") or source.get("id")),
            rule_id=_text(source.get("rule_id")),
            source=_text(source.get("source") or "unknown", "unknown"),
            metric_name=_text(source.get("metric_name") or source.get("name")),
            current_value=_value(source.get("current_value")),
            baseline_value=_value(source.get("baseline_value")),
            delta=None if source.get("delta") is None else safe_float_value(source.get("delta"), 0.0),
            delta_ratio=None if source.get("delta_ratio") is None else safe_float_value(source.get("delta_ratio"), 0.0),
            threshold=None if source.get("threshold") is None else safe_float_value(source.get("threshold"), 0.0),
            triggered=_bool(source.get("triggered")),
            severity=_choice(source.get("severity"), SEVERITIES, "warning"),
            reason_codes=[str(item) for item in clean_list(source.get("reason_codes") or [])],
            created_at=_text(source.get("created_at") or utc_now_iso()),
            raw_payload=clean_dict(source.get("raw_payload") or {}),
        )


@dataclass
class AlertRule:
    rule_id: str = ""
    alert_name: str = ""
    source: str | None = None
    condition_type: str = "drift_signal_triggered"
    metric_name: str | None = None
    severity: str = "warning"
    enabled: bool = True
    threshold: float | None = None
    description: str = ""
    created_at: str = field(default_factory=utc_now_iso)
    raw_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["rule_id"] = _text(self.rule_id or f"alert_rule:{self.alert_name or self.condition_type}")
        data["alert_name"] = _text(self.alert_name or self.condition_type)
        data["source"] = None if self.source in {None, ""} else str(self.source)
        data["condition_type"] = _choice(self.condition_type, CONDITION_TYPES, "drift_signal_triggered")
        data["metric_name"] = None if self.metric_name in {None, ""} else str(self.metric_name)
        data["severity"] = _choice(self.severity, SEVERITIES, "warning")
        data["enabled"] = _bool(self.enabled, True)
        data["threshold"] = None if self.threshold is None else safe_float_value(self.threshold, 0.0)
        data["description"] = _text(self.description)
        data["created_at"] = _text(self.created_at or utc_now_iso())
        data["raw_payload"] = clean_dict(self.raw_payload)
        return clean_dict(data)

    @classmethod
    def from_dict(cls, data: Any) -> "AlertRule":
        source = data.to_dict() if isinstance(data, AlertRule) else (data if isinstance(data, dict) else {})
        return cls(
            rule_id=_text(source.get("rule_id") or source.get("id")),
            alert_name=_text(source.get("alert_name") or source.get("name")),
            source=None if source.get("source") in {None, ""} else str(source.get("source")),
            condition_type=_choice(source.get("condition_type"), CONDITION_TYPES, "drift_signal_triggered"),
            metric_name=None if source.get("metric_name") in {None, ""} else str(source.get("metric_name")),
            severity=_choice(source.get("severity"), SEVERITIES, "warning"),
            enabled=_bool(source.get("enabled"), True),
            threshold=None if source.get("threshold") is None else safe_float_value(source.get("threshold"), 0.0),
            description=_text(source.get("description")),
            created_at=_text(source.get("created_at") or utc_now_iso()),
            raw_payload=clean_dict(source.get("raw_payload") or {}),
        )


@dataclass
class AlertEvent:
    alert_id: str = ""
    rule_id: str = ""
    alert_name: str = ""
    source: str = "unknown"
    severity: str = "warning"
    status: str = "open"
    message: str = ""
    triggered: bool = True
    created_at: str = field(default_factory=utc_now_iso)
    metric_name: str | None = None
    metric_value: int | float | str | bool | None = None
    reason_codes: list[str] = field(default_factory=list)
    raw_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["alert_id"] = _text(self.alert_id or f"alert:{self.rule_id}:{self.source}:{self.created_at}")
        data["rule_id"] = _text(self.rule_id)
        data["alert_name"] = _text(self.alert_name)
        data["source"] = _text(self.source or "unknown", "unknown")
        data["severity"] = _choice(self.severity, SEVERITIES, "warning")
        data["status"] = _choice(self.status, ALERT_STATUSES, "open")
        data["message"] = _text(self.message)
        data["triggered"] = _bool(self.triggered, True)
        data["created_at"] = _text(self.created_at or utc_now_iso())
        data["metric_name"] = None if self.metric_name in {None, ""} else str(self.metric_name)
        data["metric_value"] = _value(self.metric_value)
        data["reason_codes"] = [str(item) for item in clean_list(self.reason_codes)]
        data["raw_payload"] = clean_dict(self.raw_payload)
        return clean_dict(data)

    @classmethod
    def from_dict(cls, data: Any) -> "AlertEvent":
        source = data.to_dict() if isinstance(data, AlertEvent) else (data if isinstance(data, dict) else {})
        return cls(
            alert_id=_text(source.get("alert_id") or source.get("id")),
            rule_id=_text(source.get("rule_id")),
            alert_name=_text(source.get("alert_name") or source.get("name")),
            source=_text(source.get("source") or "unknown", "unknown"),
            severity=_choice(source.get("severity"), SEVERITIES, "warning"),
            status=_choice(source.get("status"), ALERT_STATUSES, "open"),
            message=_text(source.get("message")),
            triggered=_bool(source.get("triggered"), True),
            created_at=_text(source.get("created_at") or utc_now_iso()),
            metric_name=None if source.get("metric_name") in {None, ""} else str(source.get("metric_name")),
            metric_value=_value(source.get("metric_value")),
            reason_codes=[str(item) for item in clean_list(source.get("reason_codes") or [])],
            raw_payload=clean_dict(source.get("raw_payload") or {}),
        )


@dataclass
class HealthDiagnosis:
    diagnosis_id: str = ""
    area: str = "overall"
    status: str = "unknown"
    severity: str = "info"
    summary: str = ""
    evidence_metrics: list[str] = field(default_factory=list)
    alert_ids: list[str] = field(default_factory=list)
    drift_signal_ids: list[str] = field(default_factory=list)
    recommended_action: str = "no_action_required"
    auto_action_allowed: bool = False
    created_at: str = field(default_factory=utc_now_iso)
    raw_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["diagnosis_id"] = _text(self.diagnosis_id or f"diagnosis:{self.area}:{self.created_at}")
        data["area"] = _choice(self.area, AREAS, "overall")
        data["status"] = _choice(self.status, DIAGNOSIS_STATUSES, "unknown")
        data["severity"] = _choice(self.severity, SEVERITIES, "info")
        data["summary"] = _text(self.summary)
        data["evidence_metrics"] = [str(item) for item in clean_list(self.evidence_metrics)]
        data["alert_ids"] = [str(item) for item in clean_list(self.alert_ids)]
        data["drift_signal_ids"] = [str(item) for item in clean_list(self.drift_signal_ids)]
        data["recommended_action"] = _text(self.recommended_action or "no_action_required", "no_action_required")
        data["auto_action_allowed"] = False
        data["created_at"] = _text(self.created_at or utc_now_iso())
        data["raw_payload"] = clean_dict(self.raw_payload)
        return clean_dict(data)

    @classmethod
    def from_dict(cls, data: Any) -> "HealthDiagnosis":
        source = data.to_dict() if isinstance(data, HealthDiagnosis) else (data if isinstance(data, dict) else {})
        return cls(
            diagnosis_id=_text(source.get("diagnosis_id") or source.get("id")),
            area=_choice(source.get("area"), AREAS, "overall"),
            status=_choice(source.get("status"), DIAGNOSIS_STATUSES, "unknown"),
            severity=_choice(source.get("severity"), SEVERITIES, "info"),
            summary=_text(source.get("summary")),
            evidence_metrics=[str(item) for item in clean_list(source.get("evidence_metrics") or [])],
            alert_ids=[str(item) for item in clean_list(source.get("alert_ids") or [])],
            drift_signal_ids=[str(item) for item in clean_list(source.get("drift_signal_ids") or [])],
            recommended_action=_text(source.get("recommended_action") or "no_action_required", "no_action_required"),
            auto_action_allowed=False,
            created_at=_text(source.get("created_at") or utc_now_iso()),
            raw_payload=clean_dict(source.get("raw_payload") or {}),
        )


@dataclass
class HealthDiagnosisReport:
    report_id: str = ""
    generated_at: str = field(default_factory=utc_now_iso)
    mode: str = "advisory"
    overall_status: str = "unknown"
    diagnoses: list[HealthDiagnosis] = field(default_factory=list)
    alert_events: list[AlertEvent] = field(default_factory=list)
    drift_signals: list[DriftSignal] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    raw_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["report_id"] = _text(self.report_id or f"health_diagnosis_report:{self.generated_at}")
        data["generated_at"] = _text(self.generated_at or utc_now_iso())
        data["mode"] = "advisory"
        data["overall_status"] = _choice(self.overall_status, DIAGNOSIS_STATUSES, "unknown")
        data["diagnoses"] = [HealthDiagnosis.from_dict(item).to_dict() for item in list(self.diagnoses or [])]
        data["alert_events"] = [AlertEvent.from_dict(item).to_dict() for item in list(self.alert_events or [])]
        data["drift_signals"] = [DriftSignal.from_dict(item).to_dict() for item in list(self.drift_signals or [])]
        data["summary"] = clean_dict(self.summary)
        data["warnings"] = [str(item) for item in clean_list(self.warnings)]
        data["raw_payload"] = clean_dict(self.raw_payload)
        return clean_dict(data)

    @classmethod
    def from_dict(cls, data: Any) -> "HealthDiagnosisReport":
        source = data.to_dict() if isinstance(data, HealthDiagnosisReport) else (data if isinstance(data, dict) else {})
        return cls(
            report_id=_text(source.get("report_id") or source.get("id")),
            generated_at=_text(source.get("generated_at") or utc_now_iso()),
            mode="advisory",
            overall_status=_choice(source.get("overall_status"), DIAGNOSIS_STATUSES, "unknown"),
            diagnoses=[HealthDiagnosis.from_dict(item) for item in clean_list(source.get("diagnoses") or [])],
            alert_events=[AlertEvent.from_dict(item) for item in clean_list(source.get("alert_events") or source.get("alerts") or [])],
            drift_signals=[DriftSignal.from_dict(item) for item in clean_list(source.get("drift_signals") or [])],
            summary=clean_dict(source.get("summary") or {}),
            warnings=[str(item) for item in clean_list(source.get("warnings") or [])],
            raw_payload=clean_dict(source.get("raw_payload") or {}),
        )
