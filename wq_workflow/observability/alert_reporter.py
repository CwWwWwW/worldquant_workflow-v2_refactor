from __future__ import annotations

from pathlib import Path
from typing import Any

from wq_workflow import paths

from .alert_schema import AlertEvent, DriftSignal
from .utils import atomic_write_json, utc_now_iso


class AlertReporter:
    def __init__(self, status_path: str | Path = "runtime/status/observability_alerts.json", *, root: str | Path | None = None, logger: Any | None = None) -> None:
        self.root = Path(root or paths.ROOT)
        target = Path(status_path)
        self.status_path = target if target.is_absolute() else self.root / target
        self.logger = logger

    def build_payload(self, alerts: list[AlertEvent], drift_signals: list[DriftSignal], warnings: list[str] | None = None) -> dict[str, Any]:
        alert_data = [AlertEvent.from_dict(alert).to_dict() for alert in list(alerts or [])]
        signal_data = [DriftSignal.from_dict(signal).to_dict() for signal in list(drift_signals or [])]
        triggered_signals = [signal for signal in signal_data if signal.get("triggered")]
        return {
            "updated_at": utc_now_iso(),
            "enabled": True,
            "mode": "advisory",
            "alerts": alert_data,
            "drift_signals": signal_data,
            "summary": {
                "alert_count": len([alert for alert in alert_data if alert.get("triggered")]),
                "critical_count": len([alert for alert in alert_data if alert.get("triggered") and alert.get("severity") == "critical"]),
                "warning_count": len([alert for alert in alert_data if alert.get("triggered") and alert.get("severity") == "warning"]),
                "triggered_drift_count": len(triggered_signals),
            },
            "warnings": [str(item) for item in list(warnings or [])],
        }

    def write_report(self, alerts: list[AlertEvent], drift_signals: list[DriftSignal], warnings: list[str] | None = None) -> dict[str, Any]:
        payload = self.build_payload(alerts, drift_signals, warnings)
        result = atomic_write_json(self.status_path, payload, backup_corrupt=True)
        if not result.get("ok"):
            self._warn("observability alert report write failed: %s", result.get("error"))
        return result

    def update(self, alerts: list[AlertEvent], drift_signals: list[DriftSignal], warnings: list[str] | None = None) -> dict[str, Any]:
        return self.write_report(alerts, drift_signals, warnings)

    def _warn(self, message: str, value: Any) -> None:
        try:
            if self.logger is not None:
                self.logger.warning(message, value)
        except Exception:
            pass
