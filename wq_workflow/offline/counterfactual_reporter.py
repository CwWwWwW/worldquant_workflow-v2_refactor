from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from wq_workflow.data.json_utils import to_jsonable

from .schema import CounterfactualEstimate, CounterfactualSummary, utc_now_iso


class CounterfactualReporter:
    def __init__(self, *, repository: Any | None = None, status_path: str | Path = "runtime/status/counterfactual_report.json", logger: Any | None = None) -> None:
        self.repository = repository
        self.status_path = Path(status_path)
        self.logger = logger
        self.warnings: list[str] = []

    def update(self, *, enabled: bool = False, mode: str = "advisory", latest_replay_run_id: str | None = None, warnings: list[str] | None = None) -> dict[str, Any]:
        warnings_out = (warnings or []) + list(self.warnings)
        try:
            summaries = self.repository.list_summaries() if self.repository is not None else []
            all_estimates = self.repository.list_estimates(limit=100000) if self.repository is not None else []
            recent = all_estimates[:20]
            requests = self.repository.list_requests(limit=100000) if self.repository is not None else []
            payload = {
                "updated_at": utc_now_iso(),
                "enabled": bool(enabled),
                "mode": str(mode or "advisory"),
                "latest_replay_run_id": latest_replay_run_id or _latest_replay_id(requests),
                "request_count": len(requests),
                "estimate_count": len(all_estimates),
                "summaries": [_summary_payload(item) for item in summaries],
                "recent_estimates": [_estimate_payload(item) for item in recent],
                "warnings": warnings_out[-50:],
            }
            self._write_atomic(payload)
            return {"ok": True, "status_path": str(self.status_path), **payload}
        except Exception as exc:
            message = f"counterfactual_report_write_failed: {exc}"
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
                self.logger.warning("counterfactual reporter: %s", message)
        except Exception:
            pass


def _latest_replay_id(requests: list[Any]) -> str:
    for request in requests or []:
        value = getattr(request, "replay_run_id", None)
        if value:
            return str(value)
    return ""


def _summary_payload(summary: CounterfactualSummary | dict[str, Any]) -> dict[str, Any]:
    data = CounterfactualSummary.from_dict(summary).to_dict()
    return {
        "decision_type": data.get("decision_type"),
        "request_count": data.get("request_count"),
        "estimate_count": data.get("estimate_count"),
        "insufficient_count": data.get("insufficient_count"),
        "high_risk_count": data.get("high_risk_count"),
        "medium_or_high_confidence_count": data.get("medium_or_high_confidence_count"),
        "avg_evidence_count": data.get("avg_evidence_count"),
    }


def _estimate_payload(estimate: CounterfactualEstimate | dict[str, Any]) -> dict[str, Any]:
    data = CounterfactualEstimate.from_dict(estimate).to_dict()
    return {
        "decision_id": data.get("decision_id"),
        "verdict": data.get("verdict"),
        "confidence": data.get("confidence"),
        "evidence_count": data.get("evidence_count"),
        "estimated_not_observed": data.get("estimated_not_observed"),
        "risk_flags": data.get("risk_flags") or [],
    }
