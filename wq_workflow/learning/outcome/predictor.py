from __future__ import annotations

from typing import Any

from wq_workflow.learning.ml.prediction_audit import safe_audit_prediction
from wq_workflow.learning.ml.training_utils import flatten_feature_dict


def _prob(model: Any, vector: list[float]) -> float | None:
    try:
        if hasattr(model, "predict_proba"):
            p = model.predict_proba([vector])[0]
            return float(p[1] if len(p) > 1 else p[0])
        return float(model.predict([vector])[0])
    except Exception:
        return None


class OutcomePredictor:
    def __init__(self, *, model_registry: Any, audit_logger: Any | None = None, config: Any | None = None) -> None:
        self.model_registry = model_registry; self.audit_logger = audit_logger; self.config = config

    def predict(self, features: dict[str, Any] | None, *, alpha_id: str = "") -> dict[str, Any]:
        flat = flatten_feature_dict(features or {})
        try:
            active = self.model_registry.load_active_model("simulator") if self.model_registry else None
            if not active:
                result = {"source": "no_model_or_dependency_unavailable", "expected_reward": 0.0, "success_probability": 0.0, "failure_probability": 1.0, "high_turnover_risk": 0.0, "skip_risk": 0.5, "confidence": 0.0, "model_version": "", "explain": "no active simulator model"}
            else:
                vector = active["feature_schema"].transform_one(flat); bundle = active["model"].get("models", active["model"])
                reward_model = bundle.get("reward_regressor"); success_model = bundle.get("success_classifier"); turnover_model = bundle.get("high_turnover_classifier")
                reward = float(reward_model.predict([vector])[0]) if reward_model is not None else 0.0
                success = _prob(success_model, vector) if success_model is not None else 0.5
                turnover = _prob(turnover_model, vector) if turnover_model is not None else 0.0
                failure = max(0.0, min(1.0, 1.0 - float(success or 0.0)))
                skip_risk = failure * 0.50 + float(turnover or 0.0) * 0.20 + max(0.0, -reward) * 0.30
                result = {"source": "learned_simulator_observe", "expected_reward": reward, "success_probability": float(success or 0.0), "failure_probability": failure, "high_turnover_risk": float(turnover or 0.0), "skip_risk": float(skip_risk), "confidence": float(getattr(self.config, "ml_model_min_confidence", 0.65) or 0.65), "model_version": active.get("model_version", ""), "explain": "simulator observe prediction from active model"}
            safe_audit_prediction(self.audit_logger, task_name="simulator", alpha_id=alpha_id, model_version=result.get("model_version", ""), features=flat, prediction=result, confidence=result.get("confidence"), final_decision="observe_simulator", final_source=result.get("source", "learned_simulator_observe"))
            return result
        except Exception as exc:
            return {"source": "no_model_or_dependency_unavailable", "error": str(exc), "expected_reward": 0.0, "success_probability": 0.0, "failure_probability": 1.0, "high_turnover_risk": 0.0, "skip_risk": 0.5, "confidence": 0.0, "model_version": "", "explain": "simulator prediction failed"}
