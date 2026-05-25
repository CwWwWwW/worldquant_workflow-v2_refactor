from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from wq_workflow.data.json_utils import to_jsonable

from .schema import StrategyScoreboard, utc_now_iso


class StrategyReporter:
    def __init__(self, *, status_path: str | Path = "runtime/status/strategy_scoreboard.json", logger: Any | None = None) -> None:
        self.status_path = Path(status_path)
        self.logger = logger
        self.warnings: list[str] = []

    def update(self, scoreboard: StrategyScoreboard | dict[str, Any] | None, *, enabled: bool = True, mode: str = "advisory", warnings: list[str] | None = None) -> dict[str, Any]:
        warnings_out = (warnings or []) + list(self.warnings)
        try:
            board = StrategyScoreboard.from_dict(scoreboard or {})
            payload = {
                "updated_at": utc_now_iso(),
                "enabled": bool(enabled),
                "mode": str(mode or "advisory"),
                "scoreboard_id": board.scoreboard_id,
                "strategies": [
                    {
                        "strategy_id": score.strategy_id,
                        "strategy_type": score.strategy_type,
                        "total_score": score.total_score,
                        "confidence": score.confidence,
                        "risk_level": score.risk_level,
                        "recommendation": score.recommendation,
                        "sample_count": score.sample_count,
                        "reason_codes": score.reason_codes,
                        "risk_flags": score.risk_flags,
                    }
                    for score in board.scores
                ],
                "evidence_summary": board.evidence_summary,
                "warnings": list(dict.fromkeys((board.warnings or []) + warnings_out))[-100:],
            }
            self._write_atomic(payload)
            return {"ok": True, "status_path": str(self.status_path), **payload}
        except Exception as exc:
            message = f"strategy_report_write_failed: {exc}"
            self._warn(message)
            return {"ok": False, "enabled": bool(enabled), "status_path": str(self.status_path), "warnings": (warnings_out + [message])[-100:]}

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
                self.logger.warning("strategy reporter: %s", message)
        except Exception:
            pass
