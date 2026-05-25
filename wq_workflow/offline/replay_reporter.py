from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from wq_workflow.data.json_utils import to_jsonable

from .schema import ReplayComparison, ReplayPolicyMetrics, ReplayRun, utc_now_iso


class ReplayReporter:
    def __init__(self, *, repository: Any | None = None, status_path: str | Path = "runtime/status/offline_replay_report.json", logger: Any | None = None) -> None:
        self.repository = repository
        self.status_path = Path(status_path)
        self.logger = logger
        self.warnings: list[str] = []

    def update(self, *, enabled: bool = False, mode: str = "advisory", latest_replay_run_id: str | None = None, warnings: list[str] | None = None) -> dict[str, Any]:
        warnings_out = (warnings or []) + list(self.warnings)
        try:
            runs = self.repository.list_replay_runs(limit=20) if self.repository is not None else []
            latest_id = latest_replay_run_id or (runs[0].replay_run_id if runs else "")
            metrics = self.repository.list_policy_metrics(latest_id) if self.repository is not None and latest_id else []
            comparisons = self.repository.list_comparisons(latest_id) if self.repository is not None and latest_id else []
            payload = {
                "updated_at": utc_now_iso(),
                "enabled": bool(enabled),
                "mode": str(mode or "advisory"),
                "latest_replay_run_id": latest_id,
                "runs": [_run_payload(item) for item in runs],
                "metrics": [_metrics_payload(item) for item in metrics],
                "comparisons": [_comparison_payload(item) for item in comparisons],
                "warnings": warnings_out[-50:],
            }
            self._write_atomic(payload)
            return {"ok": True, "status_path": str(self.status_path), **payload}
        except Exception as exc:
            message = f"offline_replay_report_write_failed: {exc}"
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
                self.logger.warning("offline replay reporter: %s", message)
        except Exception:
            pass


def _run_payload(run: ReplayRun | dict[str, Any]) -> dict[str, Any]:
    data = ReplayRun.from_dict(run).to_dict()
    return {
        "replay_run_id": data.get("replay_run_id"),
        "name": data.get("name"),
        "status": data.get("status"),
        "sample_count": data.get("sample_count"),
        "observable_count": data.get("observable_count"),
        "policies": data.get("policies") or [],
    }


def _metrics_payload(metrics: ReplayPolicyMetrics | dict[str, Any]) -> dict[str, Any]:
    data = ReplayPolicyMetrics.from_dict(metrics).to_dict()
    return {
        "policy_name": data.get("policy_name"),
        "decision_type": data.get("decision_type"),
        "sample_count": data.get("sample_count"),
        "observable_count": data.get("observable_count"),
        "coverage_rate": data.get("coverage_rate"),
        "avg_reward": data.get("avg_reward"),
        "success_rate": data.get("success_rate"),
        "avg_platform_sc_abs_max": data.get("avg_platform_sc_abs_max"),
        "quality_pass_rate": data.get("quality_pass_rate"),
    }


def _comparison_payload(comparison: ReplayComparison | dict[str, Any]) -> dict[str, Any]:
    data = ReplayComparison.from_dict(comparison).to_dict()
    return {
        "baseline_policy": data.get("baseline_policy"),
        "challenger_policy": data.get("challenger_policy"),
        "verdict": data.get("verdict"),
        "confidence": data.get("confidence"),
        "reward_delta": data.get("reward_delta"),
        "success_rate_delta": data.get("success_rate_delta"),
        "sc_risk_delta": data.get("sc_risk_delta"),
    }
