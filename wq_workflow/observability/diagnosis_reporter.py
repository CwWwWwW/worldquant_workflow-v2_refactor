from __future__ import annotations

from pathlib import Path
from typing import Any

from wq_workflow import paths

from .alert_schema import HealthDiagnosisReport
from .utils import atomic_write_json, utc_now_iso


class DiagnosisReporter:
    def __init__(self, status_path: str | Path = "runtime/status/health_diagnosis.json", *, root: str | Path | None = None, logger: Any | None = None) -> None:
        self.root = Path(root or paths.ROOT)
        target = Path(status_path)
        self.status_path = target if target.is_absolute() else self.root / target
        self.logger = logger

    def build_payload(self, report: HealthDiagnosisReport) -> dict[str, Any]:
        data = HealthDiagnosisReport.from_dict(report).to_dict()
        diagnoses = data.get("diagnoses", [])
        for diagnosis in diagnoses:
            diagnosis["auto_action_allowed"] = False
        return {
            "updated_at": utc_now_iso(),
            "enabled": True,
            "mode": "advisory",
            "overall_status": data.get("overall_status", "unknown"),
            "diagnoses": diagnoses,
            "summary": data.get("summary", {}),
            "warnings": data.get("warnings", []),
        }

    def write_report(self, report: HealthDiagnosisReport) -> dict[str, Any]:
        payload = self.build_payload(report)
        result = atomic_write_json(self.status_path, payload, backup_corrupt=True)
        if not result.get("ok"):
            self._warn("observability diagnosis report write failed: %s", result.get("error"))
        return result

    def update(self, report: HealthDiagnosisReport) -> dict[str, Any]:
        return self.write_report(report)

    def _warn(self, message: str, value: Any) -> None:
        try:
            if self.logger is not None:
                self.logger.warning(message, value)
        except Exception:
            pass
