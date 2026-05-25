from __future__ import annotations

from pathlib import Path
from typing import Any

from wq_workflow import paths

from .schema import ObservabilitySnapshot, ObservabilitySummary
from .utils import atomic_write_json, utc_now_iso


class ObservabilityReporter:
    def __init__(self, status_path: str | Path = "runtime/status/observability_metrics.json", *, root: str | Path | None = None, logger: Any | None = None) -> None:
        self.root = Path(root or paths.ROOT)
        target = Path(status_path)
        self.status_path = target if target.is_absolute() else self.root / target
        self.logger = logger

    def build_payload(self, snapshot: ObservabilitySnapshot, summary: ObservabilitySummary) -> dict[str, Any]:
        snapshot_data = ObservabilitySnapshot.from_dict(snapshot).to_dict()
        summary_data = ObservabilitySummary.from_dict(summary).to_dict()
        return {
            "updated_at": utc_now_iso(),
            "enabled": True,
            "mode": "metrics_only",
            "snapshot_id": snapshot_data.get("snapshot_id"),
            "summary": {
                "total_metrics": summary_data.get("total_metrics", 0),
                "available_sources": summary_data.get("available_sources", 0),
                "stale_sources": summary_data.get("stale_sources", 0),
                "warning_count": summary_data.get("warning_count", 0),
                "workflow": summary_data.get("workflow_summary", {}),
                "ml": summary_data.get("ml_summary", {}),
                "governance": summary_data.get("governance_summary", {}),
                "experiment": summary_data.get("experiment_summary", {}),
                "offline": summary_data.get("offline_summary", {}),
                "strategy": summary_data.get("strategy_summary", {}),
                "system": summary_data.get("system_summary", {}),
            },
            "sources": snapshot_data.get("source_statuses", []),
            "metrics": snapshot_data.get("metrics", []),
            "warnings": snapshot_data.get("warnings", []) + summary_data.get("warnings", []),
        }

    def write_report(self, snapshot: ObservabilitySnapshot, summary: ObservabilitySummary) -> dict[str, Any]:
        payload = self.build_payload(snapshot, summary)
        result = atomic_write_json(self.status_path, payload, backup_corrupt=True)
        if not result.get("ok"):
            try:
                if self.logger is not None:
                    self.logger.warning("observability report write failed: %s", result.get("error"))
            except Exception:
                pass
        return result

    def update(self, snapshot: ObservabilitySnapshot, summary: ObservabilitySummary) -> dict[str, Any]:
        return self.write_report(snapshot, summary)
