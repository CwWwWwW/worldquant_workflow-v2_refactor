from __future__ import annotations

from typing import Any

from .schema import ObservabilityMetric, ObservabilitySourceStatus
from .source_adapters import (
    ExperimentMetricsAdapter,
    GovernanceMetricsAdapter,
    MLMetricsAdapter,
    OfflineMetricsAdapter,
    StrategyMetricsAdapter,
    SystemMetricsAdapter,
    WorkflowStatusAdapter,
)
from .utils import clean_dict, clean_list, utc_now_iso


class BaseMetricsCollector:
    source = "unknown"

    def __init__(self, adapter: Any | None = None, *, config: Any | None = None, db_path: Any | None = None, root: Any | None = None) -> None:
        self.config = config
        self.adapter = adapter or self.adapter_cls(config=config, db_path=db_path, root=root)  # type: ignore[attr-defined]

    def collect(self) -> tuple[list[ObservabilityMetric], ObservabilitySourceStatus]:
        timestamp = utc_now_iso()
        try:
            result = self.adapter.collect()
            metrics: list[ObservabilityMetric] = []
            for idx, item in enumerate(clean_list(result.get("metrics") or [])):
                if not isinstance(item, dict):
                    continue
                source = str(item.get("source") or result.get("source") or self.source)
                name = str(item.get("metric_name") or item.get("name") or "")
                metric_id = str(item.get("metric_id") or f"{source}:{name}:{timestamp}:{idx}")
                metrics.append(
                    ObservabilityMetric(
                        metric_id=metric_id,
                        source=source,
                        metric_name=name,
                        metric_type=str(item.get("metric_type") or "gauge"),
                        value=item.get("value"),
                        unit=item.get("unit"),
                        timestamp=str(item.get("timestamp") or timestamp),
                        tags=clean_dict(item.get("tags") or {}),
                        raw_payload=clean_dict(item.get("raw_payload") or {}),
                    )
                )
            warnings = [str(item) for item in clean_list(result.get("warnings") or [])]
            status = ObservabilitySourceStatus(
                source=str(result.get("source") or self.source),
                available=bool(result.get("available")),
                status_path=result.get("status_path"),
                table_names=[str(item) for item in clean_list(result.get("table_names") or [])],
                last_updated_at=result.get("last_updated_at"),
                is_stale=bool(result.get("is_stale")),
                metric_count=len(metrics),
                warnings=warnings,
                raw_payload=clean_dict(result.get("raw_payload") or {}),
            )
            return metrics, status
        except Exception as exc:
            status = ObservabilitySourceStatus(source=self.source, available=False, metric_count=0, warnings=[f"collector_failed:{exc}"], raw_payload={"fail_open": True})
            return [], status


class WorkflowMetricsCollector(BaseMetricsCollector):
    source = "workflow"
    adapter_cls = WorkflowStatusAdapter


class MLMetricsCollector(BaseMetricsCollector):
    source = "ml"
    adapter_cls = MLMetricsAdapter


class GovernanceMetricsCollector(BaseMetricsCollector):
    source = "governance"
    adapter_cls = GovernanceMetricsAdapter


class ExperimentMetricsCollector(BaseMetricsCollector):
    source = "experiment"
    adapter_cls = ExperimentMetricsAdapter


class OfflineMetricsCollector(BaseMetricsCollector):
    source = "offline_replay"
    adapter_cls = OfflineMetricsAdapter


class StrategyMetricsCollector(BaseMetricsCollector):
    source = "strategy"
    adapter_cls = StrategyMetricsAdapter


class SystemMetricsCollector(BaseMetricsCollector):
    source = "system"
    adapter_cls = SystemMetricsAdapter
