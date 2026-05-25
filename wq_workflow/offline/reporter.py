from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from wq_workflow.data.json_utils import to_jsonable

from .schema import DecisionSnapshotSummary, utc_now_iso


class DecisionSnapshotReporter:
    def __init__(self, *, repository: Any | None = None, status_path: str | Path = "runtime/status/decision_snapshot_status.json", logger: Any | None = None) -> None:
        self.repository = repository
        self.status_path = Path(status_path)
        self.logger = logger
        self.warnings: list[str] = []

    def update(self, *, enabled: bool = True, warnings: list[str] | None = None) -> dict[str, Any]:
        warnings_out = list(warnings or []) + list(self.warnings)
        try:
            summaries = self.repository.list_summaries() if self.repository is not None else []
            snapshot_count = self.repository.count_snapshots() if self.repository is not None and hasattr(self.repository, "count_snapshots") else 0
            outcome_count = self.repository.count_outcomes() if self.repository is not None and hasattr(self.repository, "count_outcomes") else 0
            payload = {
                "updated_at": utc_now_iso(),
                "enabled": bool(enabled),
                "snapshot_count": int(snapshot_count or 0),
                "outcome_count": int(outcome_count or 0),
                "summaries": [_summary_payload(item) for item in summaries],
                "warnings": warnings_out[-50:],
            }
            self._write_atomic(payload)
            return {"ok": True, "status_path": str(self.status_path), **payload}
        except Exception as exc:
            message = f"decision_snapshot_report_write_failed: {exc}"
            self._warn(message)
            return {"ok": False, "enabled": bool(enabled), "status_path": str(self.status_path), "warnings": (warnings_out + [message])[-50:]}

    def _write_atomic(self, payload: dict[str, Any]) -> None:
        path = self.status_path
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            try:
                json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                backup = path.with_suffix(path.suffix + f".corrupt.{utc_now_iso().replace(':', '').replace('+', '_')}.bak")
                try:
                    path.replace(backup)
                except Exception:
                    pass
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(to_jsonable(payload), ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)

    def _warn(self, message: str) -> None:
        self.warnings.append(message)
        self.warnings = self.warnings[-50:]
        try:
            if self.logger is not None:
                self.logger.warning("decision snapshot reporter: %s", message)
        except Exception:
            pass


def _summary_payload(summary: Any) -> dict[str, Any]:
    if isinstance(summary, DecisionSnapshotSummary):
        data = summary.to_dict()
    elif hasattr(summary, "to_dict"):
        data = summary.to_dict()
    elif isinstance(summary, dict):
        data = dict(summary)
    else:
        data = {}
    return {
        "decision_type": str(data.get("decision_type") or "unknown"),
        "sample_count": int(data.get("sample_count") or 0),
        "outcome_count": int(data.get("outcome_count") or 0),
        "success_count": int(data.get("success_count") or 0),
        "avg_reward": data.get("avg_reward"),
        "avg_platform_sc_abs_max": data.get("avg_platform_sc_abs_max"),
    }
