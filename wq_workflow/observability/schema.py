from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .utils import clean_dict, clean_list, json_safe, safe_int_value, utc_now_iso

SOURCES = {
    "workflow",
    "platform",
    "database",
    "ml",
    "governance",
    "experiment",
    "offline_replay",
    "counterfactual",
    "strategy",
    "strategy_portfolio",
    "strategy_budget",
    "system",
    "unknown",
}
METRIC_TYPES = {"counter", "gauge", "ratio", "status", "latency", "timestamp", "text"}


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def _source(value: Any) -> str:
    text = _text(value or "unknown", "unknown").strip()
    return text if text in SOURCES else "unknown"


def _metric_type(value: Any) -> str:
    text = _text(value or "gauge", "gauge").strip()
    return text if text in METRIC_TYPES else "gauge"


def _bool(value: Any, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on", "enabled"}


@dataclass
class ObservabilityMetric:
    metric_id: str = ""
    source: str = "unknown"
    metric_name: str = ""
    metric_type: str = "gauge"
    value: int | float | str | bool | None = None
    unit: str | None = None
    timestamp: str = field(default_factory=utc_now_iso)
    tags: dict[str, Any] = field(default_factory=dict)
    raw_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["source"] = _source(self.source)
        data["metric_name"] = _text(self.metric_name)
        data["metric_type"] = _metric_type(self.metric_type)
        data["value"] = json_safe(self.value)
        data["unit"] = None if self.unit in {None, ""} else str(self.unit)
        data["timestamp"] = _text(self.timestamp or utc_now_iso())
        data["tags"] = clean_dict(self.tags)
        data["raw_payload"] = clean_dict(self.raw_payload)
        if not data["metric_id"]:
            data["metric_id"] = f"{data['source']}:{data['metric_name']}:{data['timestamp']}"
        return clean_dict(data)

    @classmethod
    def from_dict(cls, data: Any) -> "ObservabilityMetric":
        source = data.to_dict() if isinstance(data, ObservabilityMetric) else (data if isinstance(data, dict) else {})
        return cls(
            metric_id=_text(source.get("metric_id") or source.get("id")),
            source=_source(source.get("source")),
            metric_name=_text(source.get("metric_name") or source.get("name")),
            metric_type=_metric_type(source.get("metric_type") or source.get("type")),
            value=json_safe(source.get("value")),
            unit=None if source.get("unit") in {None, ""} else str(source.get("unit")),
            timestamp=_text(source.get("timestamp") or utc_now_iso()),
            tags=clean_dict(source.get("tags") or {}),
            raw_payload=clean_dict(source.get("raw_payload") or {}),
        )


@dataclass
class ObservabilitySourceStatus:
    source: str = "unknown"
    available: bool = False
    status_path: str | None = None
    table_names: list[str] = field(default_factory=list)
    last_updated_at: str | None = None
    is_stale: bool = False
    metric_count: int = 0
    warnings: list[str] = field(default_factory=list)
    raw_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["source"] = _source(self.source)
        data["available"] = _bool(self.available)
        data["status_path"] = None if self.status_path in {None, ""} else str(self.status_path)
        data["table_names"] = [str(item) for item in clean_list(self.table_names)]
        data["last_updated_at"] = None if self.last_updated_at in {None, ""} else str(self.last_updated_at)
        data["is_stale"] = _bool(self.is_stale)
        data["metric_count"] = safe_int_value(self.metric_count, 0)
        data["warnings"] = [str(item) for item in clean_list(self.warnings)]
        data["raw_payload"] = clean_dict(self.raw_payload)
        return clean_dict(data)

    @classmethod
    def from_dict(cls, data: Any) -> "ObservabilitySourceStatus":
        source = data.to_dict() if isinstance(data, ObservabilitySourceStatus) else (data if isinstance(data, dict) else {})
        return cls(
            source=_source(source.get("source")),
            available=_bool(source.get("available")),
            status_path=None if source.get("status_path") in {None, ""} else str(source.get("status_path")),
            table_names=[str(item) for item in clean_list(source.get("table_names") or [])],
            last_updated_at=None if source.get("last_updated_at") in {None, ""} else str(source.get("last_updated_at")),
            is_stale=_bool(source.get("is_stale")),
            metric_count=safe_int_value(source.get("metric_count"), 0),
            warnings=[str(item) for item in clean_list(source.get("warnings") or [])],
            raw_payload=clean_dict(source.get("raw_payload") or {}),
        )


@dataclass
class ObservabilitySnapshot:
    snapshot_id: str = ""
    generated_at: str = field(default_factory=utc_now_iso)
    metrics: list[ObservabilityMetric] = field(default_factory=list)
    source_statuses: list[ObservabilitySourceStatus] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    raw_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["snapshot_id"] = _text(self.snapshot_id or f"snapshot:{self.generated_at}")
        data["generated_at"] = _text(self.generated_at or utc_now_iso())
        data["metrics"] = [ObservabilityMetric.from_dict(item).to_dict() for item in self.metrics]
        data["source_statuses"] = [ObservabilitySourceStatus.from_dict(item).to_dict() for item in self.source_statuses]
        data["summary"] = clean_dict(self.summary)
        data["warnings"] = [str(item) for item in clean_list(self.warnings)]
        data["raw_payload"] = clean_dict(self.raw_payload)
        return clean_dict(data)

    @classmethod
    def from_dict(cls, data: Any) -> "ObservabilitySnapshot":
        source = data.to_dict() if isinstance(data, ObservabilitySnapshot) else (data if isinstance(data, dict) else {})
        return cls(
            snapshot_id=_text(source.get("snapshot_id") or source.get("id")),
            generated_at=_text(source.get("generated_at") or utc_now_iso()),
            metrics=[ObservabilityMetric.from_dict(item) for item in clean_list(source.get("metrics") or [])],
            source_statuses=[ObservabilitySourceStatus.from_dict(item) for item in clean_list(source.get("source_statuses") or source.get("sources") or [])],
            summary=clean_dict(source.get("summary") or {}),
            warnings=[str(item) for item in clean_list(source.get("warnings") or [])],
            raw_payload=clean_dict(source.get("raw_payload") or {}),
        )


@dataclass
class ObservabilitySummary:
    summary_id: str = ""
    generated_at: str = field(default_factory=utc_now_iso)
    total_metrics: int = 0
    available_sources: int = 0
    stale_sources: int = 0
    warning_count: int = 0
    workflow_summary: dict[str, Any] = field(default_factory=dict)
    ml_summary: dict[str, Any] = field(default_factory=dict)
    governance_summary: dict[str, Any] = field(default_factory=dict)
    experiment_summary: dict[str, Any] = field(default_factory=dict)
    offline_summary: dict[str, Any] = field(default_factory=dict)
    strategy_summary: dict[str, Any] = field(default_factory=dict)
    system_summary: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    raw_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["summary_id"] = _text(self.summary_id or f"summary:{self.generated_at}")
        data["generated_at"] = _text(self.generated_at or utc_now_iso())
        for key in ("total_metrics", "available_sources", "stale_sources", "warning_count"):
            data[key] = safe_int_value(data.get(key), 0)
        for key in ("workflow_summary", "ml_summary", "governance_summary", "experiment_summary", "offline_summary", "strategy_summary", "system_summary", "raw_payload"):
            data[key] = clean_dict(data.get(key) or {})
        data["warnings"] = [str(item) for item in clean_list(self.warnings)]
        return clean_dict(data)

    @classmethod
    def from_dict(cls, data: Any) -> "ObservabilitySummary":
        source = data.to_dict() if isinstance(data, ObservabilitySummary) else (data if isinstance(data, dict) else {})
        return cls(
            summary_id=_text(source.get("summary_id") or source.get("id")),
            generated_at=_text(source.get("generated_at") or utc_now_iso()),
            total_metrics=safe_int_value(source.get("total_metrics"), 0),
            available_sources=safe_int_value(source.get("available_sources"), 0),
            stale_sources=safe_int_value(source.get("stale_sources"), 0),
            warning_count=safe_int_value(source.get("warning_count"), 0),
            workflow_summary=clean_dict(source.get("workflow_summary") or source.get("workflow") or {}),
            ml_summary=clean_dict(source.get("ml_summary") or source.get("ml") or {}),
            governance_summary=clean_dict(source.get("governance_summary") or source.get("governance") or {}),
            experiment_summary=clean_dict(source.get("experiment_summary") or source.get("experiment") or {}),
            offline_summary=clean_dict(source.get("offline_summary") or source.get("offline") or {}),
            strategy_summary=clean_dict(source.get("strategy_summary") or source.get("strategy") or {}),
            system_summary=clean_dict(source.get("system_summary") or source.get("system") or {}),
            warnings=[str(item) for item in clean_list(source.get("warnings") or [])],
            raw_payload=clean_dict(source.get("raw_payload") or {}),
        )
