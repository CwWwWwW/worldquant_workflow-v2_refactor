from __future__ import annotations

from typing import Any

from wq_workflow.learning.ml.prediction_audit import safe_audit_prediction
from wq_workflow.learning.ml.training_utils import flatten_feature_dict


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


class SCPredictor:
    def __init__(self, *, model_registry: Any, audit_logger: Any | None = None, config: Any | None = None) -> None:
        self.model_registry = model_registry
        self.audit_logger = audit_logger
        self.config = config

    def predict(self, features: dict[str, Any] | None, *, alpha_id: str = "") -> dict[str, Any]:
        flat = flatten_feature_dict(features or {})
        try:
            active = self.model_registry.load_active_model("sc") if self.model_registry else None
            if not active:
                return {"source": "no_active_model", "learned_local_sc": None, "confidence": 0.0, "model_version": "", "explain": "no active SC model"}
            schema = active["feature_schema"]
            vector = schema.transform_one(flat)
            model = active["model"]
            pred = model.predict([vector])
            value = _clamp01(float(pred[0]))
            confidence = float(getattr(self.config, "ml_model_min_confidence", getattr(self.config, "sc_model_min_confidence", 0.65)) or 0.65)
            result = {"source": "learned_local", "learned_local_sc": value, "confidence": confidence, "model_version": active.get("model_version", ""), "explain": "active SC RandomForestRegressor prediction"}
            safe_audit_prediction(self.audit_logger, task_name="sc", alpha_id=alpha_id, model_version=result["model_version"], features=flat, prediction=result, confidence=confidence, final_decision="predict_sc", final_source="learned_local")
            return result
        except Exception as exc:
            return {"source": "no_model_or_dependency_unavailable", "error": str(exc), "learned_local_sc": None, "confidence": 0.0, "model_version": "", "explain": "SC prediction failed; fallback required"}
