from __future__ import annotations

from pathlib import Path
from typing import Any

from wq_workflow import paths

from .collectors import (
    ExperimentMetricsCollector,
    GovernanceMetricsCollector,
    MLMetricsCollector,
    OfflineMetricsCollector,
    StrategyMetricsCollector,
    SystemMetricsCollector,
    WorkflowMetricsCollector,
)
from .repository import ObservabilityRepository
from .reporter import ObservabilityReporter
from .schema import ObservabilityMetric, ObservabilitySnapshot, ObservabilitySourceStatus, ObservabilitySummary
from .utils import clean_dict, utc_now_iso


class ObservabilityService:
    def __init__(
        self,
        *,
        config: Any | None = None,
        storage: Any | None = None,
        db_path: str | Path | None = None,
        root: str | Path | None = None,
        logger: Any | None = None,
        repository: ObservabilityRepository | None = None,
        reporter: ObservabilityReporter | None = None,
        collectors: list[Any] | None = None,
    ) -> None:
        self.config = config
        self.storage = storage
        self.root = Path(root or paths.ROOT)
        self.db_path = db_path or getattr(config, "storage_db_path", "runtime/db/workflow.db")
        self.logger = logger
        self.repository = repository or ObservabilityRepository(storage=storage, db_path=self.db_path, logger=logger)
        self.reporter = reporter or ObservabilityReporter(getattr(config, "observability_metrics_status_path", "runtime/status/observability_metrics.json"), root=self.root, logger=logger)
        self.collectors = collectors or self._build_collectors()

    def startup_check(self) -> dict[str, Any]:
        enabled = bool(getattr(self.config, "enable_observability_metrics", True))
        try:
            init = self.repository.initialize()
            result = {
                "ok": bool(init.get("ok", False)),
                "enabled": enabled,
                "mode": getattr(self.config, "observability_mode", "metrics_only"),
                "auto_collect": bool(getattr(self.config, "observability_auto_collect", False)),
                "alerts_enabled": bool(getattr(self.config, "enable_observability_alerts", False)),
                "drift_detection_enabled": bool(getattr(self.config, "enable_observability_drift_detection", False)),
                "diagnosis_enabled": bool(getattr(self.config, "enable_observability_diagnosis", False)),
                "explainability_enabled": False,
            }
            if enabled and bool(getattr(self.config, "observability_auto_collect", False)):
                result["collect"] = self.collect_metrics()
            return result
        except Exception as exc:
            self._warn("observability startup failed: %s", exc)
            return {"ok": bool(getattr(self.config, "observability_fail_open", True)), "enabled": enabled, "fail_open": True, "error": str(exc)}

    def collect_metrics(self) -> dict[str, Any]:
        try:
            metrics: list[ObservabilityMetric] = []
            statuses: list[ObservabilitySourceStatus] = []
            warnings: list[str] = []
            for collector in self.collectors:
                try:
                    collected, status = collector.collect()
                    metrics.extend(collected)
                    statuses.append(status)
                    warnings.extend(status.warnings or [])
                except Exception as exc:
                    warnings.append(f"collector_failed:{getattr(collector, 'source', 'unknown')}:{exc}")
            generated_at = utc_now_iso()
            summary = self._build_summary(metrics, statuses, warnings, generated_at)
            snapshot = ObservabilitySnapshot(
                snapshot_id=f"observability_snapshot:{generated_at}",
                generated_at=generated_at,
                metrics=metrics,
                source_statuses=statuses,
                summary=summary.to_dict(),
                warnings=warnings,
                raw_payload={"mode": "metrics_only", "fail_open": True},
            )
            self.repository.save_metrics(metrics)
            for status in statuses:
                self.repository.save_source_status(status)
            self.repository.save_snapshot(snapshot)
            self.repository.save_summary(summary)
            report = self.reporter.update(snapshot, summary)
            return {"ok": True, "enabled": bool(getattr(self.config, "enable_observability_metrics", True)), "snapshot_id": snapshot.snapshot_id, "summary_id": summary.summary_id, "metric_count": len(metrics), "warnings": warnings, "report": report}
        except Exception as exc:
            self._warn("observability collect failed: %s", exc)
            return {"ok": bool(getattr(self.config, "observability_fail_open", True)), "fail_open": True, "error": str(exc)}

    def get_latest_snapshot(self) -> ObservabilitySnapshot | None:
        return self.repository.get_latest_snapshot()

    def get_latest_summary(self) -> ObservabilitySummary | None:
        return self.repository.get_latest_summary()

    def get_source_status(self, source: str) -> ObservabilitySourceStatus | None:
        for status in self.repository.list_source_statuses():
            if status.source == source:
                return status
        return None

    def list_recent_metrics(self, source: str | None = None, limit: int = 1000) -> list[ObservabilityMetric]:
        return self.repository.list_metrics(source=source, limit=limit)

    def get_status(self) -> dict[str, Any]:
        latest = self.get_latest_summary()
        return {
            "enabled": bool(getattr(self.config, "enable_observability_metrics", True)),
            "mode": getattr(self.config, "observability_mode", "metrics_only"),
            "auto_collect": bool(getattr(self.config, "observability_auto_collect", False)),
            "status_path": str(getattr(self.config, "observability_metrics_status_path", "runtime/status/observability_metrics.json")),
            "latest_summary": latest.to_dict() if latest else None,
            "alerts_enabled": bool(getattr(self.config, "enable_observability_alerts", False)),
            "drift_detection_enabled": bool(getattr(self.config, "enable_observability_drift_detection", False)),
            "diagnosis_enabled": bool(getattr(self.config, "enable_observability_diagnosis", False)),
            "explainability_enabled": False,
        }

    def _build_collectors(self) -> list[Any]:
        specs = [
            ("observability_collect_workflow", WorkflowMetricsCollector),
            ("observability_collect_ml", MLMetricsCollector),
            ("observability_collect_governance", GovernanceMetricsCollector),
            ("observability_collect_experiment", ExperimentMetricsCollector),
            ("observability_collect_offline", OfflineMetricsCollector),
            ("observability_collect_strategy", StrategyMetricsCollector),
            ("observability_collect_system", SystemMetricsCollector),
        ]
        collectors: list[Any] = []
        for flag, cls in specs:
            if bool(getattr(self.config, flag, True)):
                collectors.append(cls(config=self.config, db_path=self.db_path, root=self.root))
        return collectors

    def _build_summary(self, metrics: list[ObservabilityMetric], statuses: list[ObservabilitySourceStatus], warnings: list[str], generated_at: str) -> ObservabilitySummary:
        grouped: dict[str, dict[str, Any]] = {"workflow": {}, "ml": {}, "governance": {}, "experiment": {}, "offline": {}, "strategy": {}, "system": {}}
        for metric in metrics:
            data = metric.to_dict()
            source = data.get("source")
            name = data.get("metric_name")
            if source in {"workflow"}:
                grouped["workflow"][name] = data.get("value")
            elif source in {"ml"}:
                grouped["ml"][name] = data.get("value")
            elif source in {"governance"}:
                grouped["governance"][name] = data.get("value")
            elif source in {"experiment"}:
                grouped["experiment"][name] = data.get("value")
            elif source in {"offline_replay", "counterfactual"}:
                grouped["offline"][name] = data.get("value")
            elif source in {"strategy", "strategy_portfolio", "strategy_budget"}:
                grouped["strategy"][name] = data.get("value")
            elif source in {"system"}:
                grouped["system"][name] = data.get("value")
        all_warnings = list(warnings or [])
        return ObservabilitySummary(
            summary_id=f"observability_summary:{generated_at}",
            generated_at=generated_at,
            total_metrics=len(metrics),
            available_sources=sum(1 for status in statuses if status.available),
            stale_sources=sum(1 for status in statuses if status.is_stale),
            warning_count=len(all_warnings),
            workflow_summary=clean_dict(grouped["workflow"]),
            ml_summary=clean_dict(grouped["ml"]),
            governance_summary=clean_dict(grouped["governance"]),
            experiment_summary=clean_dict(grouped["experiment"]),
            offline_summary=clean_dict(grouped["offline"]),
            strategy_summary=clean_dict(grouped["strategy"]),
            system_summary=clean_dict(grouped["system"]),
            warnings=all_warnings,
            raw_payload={"mode": "metrics_only"},
        )

    def _warn(self, message: str, exc: Exception) -> None:
        try:
            if self.logger is not None:
                self.logger.warning(message, exc)
        except Exception:
            pass
