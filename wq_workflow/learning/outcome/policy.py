from __future__ import annotations

from typing import Any


class OutcomeSimulatorPolicy:
    def __init__(self, *, config: Any, predictor: Any | None = None, audit_logger: Any | None = None, governance_service: Any | None = None) -> None:
        self.config = config
        self.predictor = predictor
        self.audit_logger = audit_logger
        self.governance_service = governance_service

    def evaluate_candidate(self, candidate: dict[str, Any] | None = None, *, features: dict[str, Any] | None = None, context: dict[str, Any] | None = None) -> dict[str, Any]:
        candidate = candidate if isinstance(candidate, dict) else {}
        alpha_id = str(candidate.get("alpha_id") or (context or {}).get("alpha_id") or "")
        prediction: dict[str, Any] | None = None
        if self.predictor is not None and getattr(self.config, "enable_simulator_model_prediction", True):
            try:
                prediction = self.predictor.predict(features or {}, alpha_id=alpha_id)
            except Exception as exc:
                prediction = {"source": "no_model_or_dependency_unavailable", "error": str(exc), "explain": "simulator policy prediction failed"}
        final_source = "legacy_simulator" if not prediction else "learned_simulator_observe"
        if self.audit_logger:
            audit = getattr(self.audit_logger, "audit", None) or getattr(self.audit_logger, "record", None)
            if callable(audit):
                try:
                    audit(task_name="simulator", alpha_id=alpha_id, model_version=(prediction or {}).get("model_version", ""), features=features or {}, prediction=prediction or {"explain": "no simulator prediction"}, confidence=(prediction or {}).get("confidence"), final_decision="run_backtest", final_source=final_source, raw_payload={"candidate": candidate, "context": context or {}})
                except Exception:
                    pass
        allow_skip = False
        if bool(getattr(self.config, "enable_simulator_model_skip", False)) and self.governance_service is not None:
            try:
                allow_skip = bool(self.governance_service.allow_hard_decision("simulator", "simulator_skip", self.config).allowed)
            except Exception:
                allow_skip = False
        return {
            "should_skip": False,
            "skip_reason": "governance_allowed_but_observe_only" if allow_skip else ("disabled" if not getattr(self.config, "enable_simulator_model_skip", False) else "governance_blocked_or_observe_only"),
            "prediction": prediction or {},
            "final_source": final_source,
        }
