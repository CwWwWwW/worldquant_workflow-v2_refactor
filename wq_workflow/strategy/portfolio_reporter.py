from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from wq_workflow.data.json_utils import to_jsonable

from .portfolio_schema import StrategyPortfolio, StrategyPortfolioReport, utc_now_iso


class StrategyPortfolioReporter:
    def __init__(self, *, status_path: str | Path = "runtime/status/strategy_portfolio_report.json", logger: Any | None = None) -> None:
        self.status_path = Path(status_path)
        self.logger = logger
        self.warnings: list[str] = []

    def update(self, portfolio: StrategyPortfolio | dict[str, Any] | None, *, enabled: bool = True, mode: str = "advisory", warnings: list[str] | None = None) -> dict[str, Any]:
        warnings_out = (warnings or []) + list(self.warnings)
        try:
            item = StrategyPortfolio.from_dict(portfolio or {})
            payload = {
                "updated_at": utc_now_iso(),
                "enabled": bool(enabled),
                "mode": str(mode or "advisory"),
                "champion_strategy_id": item.champion_strategy_id or "legacy_baseline",
                "portfolio_id": item.portfolio_id,
                "states": [
                    {
                        "strategy_id": state.strategy_id,
                        "strategy_type": state.strategy_type,
                        "current_state": state.current_state,
                        "recommended_state": state.recommended_state,
                        "current_role": state.current_role,
                        "confidence": state.confidence,
                        "risk_level": state.risk_level,
                        "score": state.score,
                        "sample_count": state.sample_count,
                        "evidence_count": state.evidence_count,
                        "governance_status": state.governance_status,
                        "reason_codes": state.reason_codes,
                        "risk_flags": state.risk_flags,
                    }
                    for state in item.states
                ],
                "transitions": [
                    {
                        "transition_id": transition.transition_id,
                        "strategy_id": transition.strategy_id,
                        "from_state": transition.from_state,
                        "to_state": transition.to_state,
                        "recommendation": transition.recommendation,
                        "allowed": bool(transition.allowed),
                        "auto_apply_allowed": False,
                        "confidence": transition.confidence,
                        "reason_codes": transition.reason_codes,
                        "risk_flags": transition.risk_flags,
                    }
                    for transition in item.transitions
                ],
                "warnings": list(dict.fromkeys((item.warnings or []) + warnings_out))[-100:],
            }
            self._write_atomic(payload)
            return {"ok": True, "status_path": str(self.status_path), **payload}
        except Exception as exc:
            message = f"strategy_portfolio_report_write_failed: {exc}"
            self._warn(message)
            return {"ok": False, "enabled": bool(enabled), "status_path": str(self.status_path), "warnings": (warnings_out + [message])[-100:]}

    def build_report(self, portfolio: StrategyPortfolio, *, mode: str = "advisory") -> StrategyPortfolioReport:
        item = StrategyPortfolio.from_dict(portfolio)
        return StrategyPortfolioReport(
            report_id=f"strategy_portfolio_report:{item.portfolio_id}",
            generated_at=utc_now_iso(),
            mode=mode or "advisory",
            champion_strategy_id=item.champion_strategy_id or "legacy_baseline",
            strategy_states=item.states,
            recommended_transitions=item.transitions,
            warnings=item.warnings,
            raw_payload={"advisory_only": True, "portfolio_id": item.portfolio_id},
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
                self.logger.warning("strategy portfolio reporter: %s", message)
        except Exception:
            pass
