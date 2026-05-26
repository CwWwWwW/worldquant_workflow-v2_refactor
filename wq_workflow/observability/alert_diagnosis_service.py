from __future__ import annotations

from pathlib import Path
from typing import Any

from wq_workflow import paths

from .alert_repository import AlertRepository
from .alert_reporter import AlertReporter
from .alert_rules import AlertRuleEngine
from .diagnosis_repository import DiagnosisRepository
from .diagnosis_reporter import DiagnosisReporter
from .drift_detector import DriftDetector
from .health_diagnosis import HealthDiagnosisService
from .repository import ObservabilityRepository
from .schema import ObservabilityMetric, ObservabilitySourceStatus


class AlertDiagnosisService:
    def __init__(
        self,
        *,
        config: Any | None = None,
        storage: Any | None = None,
        db_path: str | Path | None = None,
        root: str | Path | None = None,
        logger: Any | None = None,
        observability_service: Any | None = None,
        observability_repository: ObservabilityRepository | None = None,
        alert_repository: AlertRepository | None = None,
        diagnosis_repository: DiagnosisRepository | None = None,
        alert_reporter: AlertReporter | None = None,
        diagnosis_reporter: DiagnosisReporter | None = None,
        drift_detector: DriftDetector | None = None,
        alert_engine: AlertRuleEngine | None = None,
        diagnosis_service: HealthDiagnosisService | None = None,
    ) -> None:
        self.config = config
        self.storage = storage
        self.root = Path(root or paths.ROOT)
        self.db_path = db_path or getattr(config, "storage_db_path", "runtime/db/workflow.db")
        self.logger = logger
        self.observability_service = observability_service
        self.observability_repository = observability_repository or ObservabilityRepository(storage=storage, db_path=self.db_path, logger=logger)
        self.alert_repository = alert_repository or AlertRepository(storage=storage, db_path=self.db_path, logger=logger)
        self.diagnosis_repository = diagnosis_repository or DiagnosisRepository(storage=storage, db_path=self.db_path, logger=logger)
        self.alert_reporter = alert_reporter or AlertReporter(getattr(config, "observability_alerts_status_path", "runtime/status/observability_alerts.json"), root=self.root, logger=logger)
        self.diagnosis_reporter = diagnosis_reporter or DiagnosisReporter(getattr(config, "observability_diagnosis_status_path", "runtime/status/health_diagnosis.json"), root=self.root, logger=logger)
        self.drift_detector = drift_detector or DriftDetector(config=config)
        self.alert_engine = alert_engine or AlertRuleEngine(config=config)
        self.diagnosis_service = diagnosis_service or HealthDiagnosisService(config=config)
        self.last_result: dict[str, Any] | None = None

    def startup_check(self) -> dict[str, Any]:
        alerts_enabled = bool(getattr(self.config, "enable_observability_alerts", False))
        drift_enabled = bool(getattr(self.config, "enable_observability_drift_detection", False))
        diagnosis_enabled = bool(getattr(self.config, "enable_observability_diagnosis", False))
        try:
            alert_init = self.alert_repository.initialize()
            diagnosis_init = self.diagnosis_repository.initialize()
            for rule in self.drift_detector.default_rules():
                self.alert_repository.save_drift_rule(rule)
            for rule in self.alert_engine.default_rules():
                self.alert_repository.save_alert_rule(rule)
            result = {
                "ok": bool(alert_init.get("ok", False) and diagnosis_init.get("ok", False)),
                "enabled": alerts_enabled or drift_enabled or diagnosis_enabled,
                "alerts_enabled": alerts_enabled,
                "drift_detection_enabled": drift_enabled,
                "diagnosis_enabled": diagnosis_enabled,
                "mode": "advisory",
                "auto_emit": False,
                "auto_remediation": False,
                "auto_run": bool(getattr(self.config, "observability_diagnostics_auto_run", False)),
            }
            if result["enabled"] and result["auto_run"]:
                result["diagnostics"] = self.run_diagnostics()
            return result
        except Exception as exc:
            self._warn("observability alert diagnosis startup failed: %s", exc)
            return {"ok": bool(getattr(self.config, "observability_diagnosis_fail_open", True)), "enabled": alerts_enabled or drift_enabled or diagnosis_enabled, "fail_open": True, "error": str(exc)}

    def run_diagnostics(self) -> dict[str, Any]:
        try:
            metrics, statuses = self._load_observability_inputs()
            drift_signals = self.drift_detector.detect(metrics, statuses)
            alert_events = self.alert_engine.evaluate(drift_signals, statuses, metrics)
            report = self.diagnosis_service.diagnose(metrics, statuses, drift_signals, alert_events)
            for signal in drift_signals:
                self.alert_repository.save_drift_signal(signal)
            for event in alert_events:
                self.alert_repository.save_alert_event(event)
            for diagnosis in report.diagnoses:
                self.diagnosis_repository.save_diagnosis(diagnosis)
            self.diagnosis_repository.save_report(report)
            alert_write = self.alert_reporter.update(alert_events, drift_signals, warnings=report.warnings)
            diagnosis_write = self.diagnosis_reporter.update(report)
            result = {
                "ok": True,
                "mode": "advisory",
                "metric_count": len(metrics),
                "source_count": len(statuses),
                "drift_signal_count": len(drift_signals),
                "alert_count": len(alert_events),
                "overall_status": report.overall_status,
                "alert_report": alert_write,
                "diagnosis_report": diagnosis_write,
                "auto_emit": False,
                "auto_remediation": False,
            }
            self.last_result = result
            return result
        except Exception as exc:
            self._warn("observability diagnostics failed: %s", exc)
            result = {"ok": bool(getattr(self.config, "observability_diagnosis_fail_open", True)), "fail_open": True, "error": str(exc), "mode": "advisory"}
            self.last_result = result
            return result

    def get_latest_alerts(self) -> list[Any]:
        return self.alert_repository.list_alert_events(limit=1000)

    def get_latest_diagnosis(self) -> Any:
        return self.diagnosis_repository.get_latest_report()

    def list_recent_alerts(self) -> list[Any]:
        return self.alert_repository.list_alert_events(limit=int(getattr(self.config, "observability_metrics_default_limit", 1000) or 1000))

    def list_recent_drift_signals(self) -> list[Any]:
        return self.alert_repository.list_drift_signals(limit=int(getattr(self.config, "observability_metrics_default_limit", 1000) or 1000))

    def get_status(self) -> dict[str, Any]:
        latest = self.get_latest_diagnosis()
        return {
            "enabled": bool(getattr(self.config, "enable_observability_alerts", False) or getattr(self.config, "enable_observability_drift_detection", False) or getattr(self.config, "enable_observability_diagnosis", False)),
            "alerts_enabled": bool(getattr(self.config, "enable_observability_alerts", False)),
            "drift_detection_enabled": bool(getattr(self.config, "enable_observability_drift_detection", False)),
            "diagnosis_enabled": bool(getattr(self.config, "enable_observability_diagnosis", False)),
            "mode": "advisory",
            "auto_run": bool(getattr(self.config, "observability_diagnostics_auto_run", False)),
            "auto_emit": False,
            "auto_remediation": False,
            "latest_report": latest.to_dict() if latest else None,
            "last_result": self.last_result,
        }

    def _load_observability_inputs(self) -> tuple[list[ObservabilityMetric], list[ObservabilitySourceStatus]]:
        snapshot = None
        try:
            if self.observability_service is not None:
                snapshot = self.observability_service.get_latest_snapshot()
        except Exception:
            snapshot = None
        if snapshot is None:
            snapshot = self.observability_repository.get_latest_snapshot()
        if snapshot is None and self.observability_service is not None:
            try:
                self.observability_service.collect_metrics()
                snapshot = self.observability_service.get_latest_snapshot()
            except Exception as exc:
                self._warn("observability metrics fallback collect failed: %s", exc)
        if snapshot is not None:
            return list(snapshot.metrics or []), list(snapshot.source_statuses or [])
        return self.observability_repository.list_metrics(limit=int(getattr(self.config, "observability_metrics_default_limit", 1000) or 1000)), self.observability_repository.list_source_statuses()

    def _warn(self, message: str, exc: Exception) -> None:
        try:
            if self.logger is not None:
                self.logger.warning(message, exc)
        except Exception:
            pass
