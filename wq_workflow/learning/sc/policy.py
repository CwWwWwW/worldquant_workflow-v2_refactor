from __future__ import annotations

from typing import Any

from wq_workflow.data.json_utils import safe_float


class SCLearningPolicy:
    def __init__(self, *, config: Any, predictor: Any | None = None, governance_service: Any | None = None) -> None:
        self.config = config
        self.predictor = predictor
        self.governance_service = governance_service

    def decide(self, *, platform_sc: dict[str, Any] | None = None, estimated_self_corr: float | None = None, features: dict[str, Any] | None = None, alpha_id: str = "") -> dict[str, Any]:
        platform_sc = platform_sc if isinstance(platform_sc, dict) else {}
        base_prediction: dict[str, Any] = {}
        if platform_sc.get("status") == "complete":
            abs_max = safe_float(platform_sc.get("abs_max"))
            if abs_max is not None:
                return {"final_sc": abs(abs_max), "final_sc_source": "platform", "sc_confidence": 1.0, "prediction": base_prediction, "platform_sc": platform_sc}
        allow_learned_fallback = bool(getattr(self.config, "enable_sc_model_fallback", False))
        if allow_learned_fallback and self.governance_service is not None:
            try:
                allow_learned_fallback = bool(self.governance_service.allow_hard_decision("sc", "sc_fallback", self.config).allowed)
            except Exception:
                allow_learned_fallback = False
        elif allow_learned_fallback:
            allow_learned_fallback = False
        if allow_learned_fallback and self.predictor is not None:
            prediction = self.predictor.predict(features or {}, alpha_id=alpha_id)
            learned = safe_float(prediction.get("learned_local_sc"))
            confidence = safe_float(prediction.get("confidence"), 0.0) or 0.0
            min_conf = float(getattr(self.config, "sc_model_min_confidence", 0.65) or 0.65)
            if learned is not None and confidence >= min_conf:
                return {"final_sc": abs(learned), "final_sc_source": "learned_local", "sc_confidence": confidence, "prediction": prediction, "platform_sc": platform_sc}
            base_prediction = prediction
        proxy = safe_float(estimated_self_corr)
        return {"final_sc": proxy, "final_sc_source": "raw_local_proxy", "sc_confidence": 0.0, "prediction": base_prediction, "platform_sc": platform_sc}
