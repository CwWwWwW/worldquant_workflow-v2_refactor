from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable


class SelfHealingGuard:
    """Lightweight non-fatal fallback wrapper for v1.2.7 stability.

    This intentionally does not implement model lifecycle, retraining,
    rollback, online evaluation, or drift governance.
    """

    def __init__(self, logger: Any | None = None, audit_path: str | Path | None = None, governance_service: Any | None = None) -> None:
        self.logger = logger
        self.audit_path = Path(audit_path) if audit_path else None
        self.governance_service = governance_service

    def _audit(self, name: str, exc: Exception) -> None:
        if self.audit_path is None:
            return
        try:
            self.audit_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {"timestamp": datetime.now().isoformat(timespec="seconds"), "name": name, "error": str(exc)}
            with self.audit_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
        except Exception:
            return

    def safe_call(self, name: str, fn: Callable[[], Any], fallback: Any = None, on_error: Callable[[Exception], Any] | None = None) -> Any:
        try:
            return fn()
        except Exception as exc:
            try:
                if self.logger is not None:
                    self.logger.warning("self-healing safe_call failed for %s: %s", name, exc)
            except Exception:
                pass
            self._audit(name, exc)
            try:
                if self.governance_service is not None:
                    lowered = str(name or "").lower()
                    task = "sc"
                    for candidate in ("parent", "policy", "simulator", "outcome", "insight", "sc"):
                        if candidate in lowered:
                            task = candidate
                            break
                    if "load" in lowered and "model" in lowered:
                        self.governance_service.handle_model_load_error(task, exc)
                    elif "predict" in lowered or "model" in lowered:
                        self.governance_service.handle_prediction_error(task, exc)
            except Exception:
                pass
            if callable(on_error):
                try:
                    on_error(exc)
                except Exception as cb_exc:
                    try:
                        if self.logger is not None:
                            self.logger.warning("self-healing on_error failed for %s: %s", name, cb_exc)
                    except Exception:
                        pass
            if callable(fallback):
                return fallback()
            return fallback
