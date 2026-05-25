from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from wq_workflow.data.json_utils import to_jsonable

from .budget_schema import StrategyBudgetPlan, StrategyBudgetReport, utc_now_iso


class StrategyBudgetReporter:
    def __init__(self, *, status_path: str | Path = "runtime/status/strategy_budget_report.json", logger: Any | None = None) -> None:
        self.status_path = Path(status_path)
        self.logger = logger
        self.warnings: list[str] = []

    def update(self, plan: StrategyBudgetPlan | dict[str, Any] | None, *, enabled: bool = True, mode: str = "advisory", warnings: list[str] | None = None) -> dict[str, Any]:
        warnings_out = (warnings or []) + list(self.warnings)
        try:
            item = StrategyBudgetPlan.from_dict(plan or {})
            payload = {
                "updated_at": utc_now_iso(),
                "enabled": bool(enabled),
                "mode": str(mode or "advisory"),
                "total_budget_hint": item.total_budget_hint,
                "plan_id": item.plan_id,
                "allocations": [allocation.to_dict() for allocation in item.allocations],
                "total_suggested_ratio": round(sum(allocation.suggested_ratio for allocation in item.allocations), 6),
                "warnings": list(dict.fromkeys((item.warnings or []) + warnings_out))[-100:],
            }
            for allocation in payload["allocations"]:
                allocation["auto_apply_allowed"] = False
            self._write_atomic(payload)
            return {"ok": True, "status_path": str(self.status_path), **payload}
        except Exception as exc:
            message = f"strategy_budget_report_write_failed: {exc}"
            self._warn(message)
            return {"ok": False, "enabled": bool(enabled), "status_path": str(self.status_path), "warnings": (warnings_out + [message])[-100:]}

    def build_report(self, plan: StrategyBudgetPlan, *, mode: str = "advisory") -> StrategyBudgetReport:
        item = StrategyBudgetPlan.from_dict(plan)
        return StrategyBudgetReport(
            report_id=f"strategy_budget_report:{item.plan_id}",
            generated_at=utc_now_iso(),
            mode=mode or "advisory",
            total_budget_hint=item.total_budget_hint,
            allocations=item.allocations,
            warnings=item.warnings,
            raw_payload={"advisory_only": True, "plan_id": item.plan_id, "auto_apply_allowed": False},
        )

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
        self.warnings = self.warnings[-100:]
        try:
            if self.logger is not None:
                self.logger.warning("strategy budget reporter: %s", message)
        except Exception:
            pass
