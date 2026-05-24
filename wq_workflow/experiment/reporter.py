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
        if self.repository is not None:
            try:
                active = [plan.to_dict() for plan in self.repository.get_active_plans()]
            except Exception as exc:
                warnings = list(warnings or []) + [f"active_experiments_unavailable: {exc}"]
            try:
                summaries = [_summary_payload(summary) for summary in self.repository.list_summaries()]
            except Exception as exc:
                warnings = list(warnings or []) + [f"summaries_unavailable: {exc}"]
        return {
            "updated_at": utc_now_iso(),
            "active_experiments": active,
            "summaries": summaries,
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


def _resolve_path(path: str | Path) -> Path:
    value = Path(path)
    return value if value.is_absolute() else ROOT / value
