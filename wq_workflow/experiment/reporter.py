from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

from wq_workflow.data.json_utils import to_jsonable
from wq_workflow.paths import ROOT

from .schema import utc_now_iso


DEFAULT_EXPERIMENT_STATUS_PATH = "runtime/status/experiment_report.json"


class ExperimentReporter:
    def __init__(self, *, repository: Any | None = None, status_path: str | Path | None = None, logger: Any | None = None) -> None:
        self.repository = repository
        self.status_path = _resolve_path(status_path or DEFAULT_EXPERIMENT_STATUS_PATH)
        self.logger = logger

    def build_report(self, *, warnings: list[str] | None = None) -> dict[str, Any]:
        active = []
        summaries = []
        budgeting = {
            "enabled": True,
            "mode": "advisory",
            "latest_budget_plan_id": None,
            "total_budget_hint": None,
            "allocations": [],
            "warnings": [],
        }
        if self.repository is not None:
            try:
                active_plans = self.repository.get_active_plans()
                active = [plan.to_dict() for plan in active_plans]
            except Exception as exc:
                active_plans = []
                warnings = list(warnings or []) + [f"active_experiments_unavailable: {exc}"]
            try:
                summaries = [_summary_payload(summary) for summary in self.repository.list_summaries()]
            except Exception as exc:
                warnings = list(warnings or []) + [f"summaries_unavailable: {exc}"]
            try:
                latest_plan = None
                for plan in active_plans:
                    latest_plan = self.repository.get_latest_budget_plan(plan.experiment_id)
                    if latest_plan is not None:
                        break
                if latest_plan is None and hasattr(self.repository, "list_budget_plans"):
                    plans = self.repository.list_budget_plans(limit=1)
                    latest_plan = plans[0] if plans else None
                if latest_plan is not None:
                    budgeting = _budgeting_payload(latest_plan)
            except Exception as exc:
                budgeting["warnings"] = [f"budgeting_unavailable: {exc}"]
        return {
            "updated_at": utc_now_iso(),
            "active_experiments": active,
            "summaries": summaries,
            "budgeting": budgeting,
            "warnings": list(warnings or []),
        }

    def write_report(self, report: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = report or self.build_report()
        try:
            self._backup_if_corrupt()
            self._atomic_write(payload)
            return {"ok": True, "path": str(self.status_path)}
        except Exception as exc:
            if self.logger is not None:
                try:
                    self.logger.warning("experiment report write failed: %s", exc)
                except Exception:
                    pass
            return {"ok": False, "error": str(exc), "path": str(self.status_path)}

    def update(self, *, warnings: list[str] | None = None) -> dict[str, Any]:
        return self.write_report(self.build_report(warnings=warnings))

    def _backup_if_corrupt(self) -> None:
        path = self.status_path
        if not path.exists():
            return
        try:
            with path.open("r", encoding="utf-8-sig") as fh:
                json.load(fh)
        except Exception:
            backup = path.with_suffix(path.suffix + f".corrupt.{utc_now_iso().replace(':', '').replace('+', '_')}")
            path.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(path, backup)
            except OSError:
                pass

    def _atomic_write(self, payload: dict[str, Any]) -> None:
        path = self.status_path
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        cleaned = to_jsonable(payload)
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(cleaned, fh, ensure_ascii=False, indent=2, allow_nan=False)
            fh.write("\n")
        os.replace(tmp, path)


def _summary_payload(summary: Any) -> dict[str, Any]:
    data = summary.to_dict() if hasattr(summary, "to_dict") else (summary if isinstance(summary, dict) else {})
    return {
        "experiment_id": data.get("experiment_id"),
        "arm_id": data.get("arm_id"),
        "sample_count": data.get("sample_count", 0),
        "success_count": data.get("success_count", 0),
        "failure_count": data.get("failure_count", 0),
        "avg_reward": data.get("avg_reward"),
        "avg_sharpe": data.get("avg_sharpe"),
        "avg_fitness": data.get("avg_fitness"),
        "avg_platform_sc_abs_max": data.get("avg_platform_sc_abs_max"),
        "quality_pass_rate": data.get("quality_pass_rate"),
    }


def _budgeting_payload(plan: Any) -> dict[str, Any]:
    data = plan.to_dict() if hasattr(plan, "to_dict") else (plan if isinstance(plan, dict) else {})
    return {
        "enabled": True,
        "mode": "advisory",
        "latest_budget_plan_id": data.get("budget_plan_id"),
        "total_budget_hint": data.get("total_budget_hint"),
        "allocations": [_allocation_payload(item) for item in (data.get("allocations") or [])],
        "warnings": [],
    }


def _allocation_payload(allocation: Any) -> dict[str, Any]:
    data = allocation.to_dict() if hasattr(allocation, "to_dict") else (allocation if isinstance(allocation, dict) else {})
    return {
        "experiment_id": data.get("experiment_id"),
        "arm_id": data.get("arm_id"),
        "suggested_ratio": data.get("suggested_ratio", 0.0),
        "min_ratio": data.get("min_ratio", 0.0),
        "max_ratio": data.get("max_ratio", 1.0),
        "sample_count": data.get("sample_count", 0),
        "success_count": data.get("success_count", 0),
        "failure_count": data.get("failure_count", 0),
        "avg_reward": data.get("avg_reward"),
        "avg_platform_sc_abs_max": data.get("avg_platform_sc_abs_max"),
        "quality_pass_rate": data.get("quality_pass_rate"),
        "status": data.get("status"),
        "reason_codes": list(data.get("reason_codes") or []),
    }


def _resolve_path(path: str | Path) -> Path:
    value = Path(path)
    return value if value.is_absolute() else ROOT / value
