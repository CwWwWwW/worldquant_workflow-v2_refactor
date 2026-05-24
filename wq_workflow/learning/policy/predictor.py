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


class PolicyPredictor:
    def __init__(self, *, model_registry: Any, audit_logger: Any | None = None, config: Any | None = None) -> None:
        self.model_registry = model_registry; self.audit_logger = audit_logger; self.config = config

    def _features_for_action(self, action: dict[str, Any], context: dict[str, Any] | None) -> dict[str, Any]:
        features = dict(context or {})
        for k, v in (action or {}).items(): features["action_" + str(k)] = v
        features.setdefault("action_type", (action or {}).get("action_type") or (action or {}).get("type") or (action or {}).get("action_id"))
        features.setdefault("legacy_score", (action or {}).get("legacy_score"))
        return flatten_feature_dict(features)

    def score_actions(self, actions: list[dict[str, Any]] | None, *, context: dict[str, Any] | None = None, alpha_id: str = "") -> list[dict[str, Any]]:
        active = None
        try:
            active = self.model_registry.load_active_model("policy") if self.model_registry else None
        except Exception:
            active = None
        scored = []
        for idx, action in enumerate(actions or []):
            features = self._features_for_action(action or {}, context)
            if not active:
                pred = {"source": "no_model_or_dependency_unavailable", "expected_reward_delta": 0.0, "success_probability": 0.0, "risk_score": 0.0, "action_score": float((action or {}).get("legacy_score") or 0.0), "confidence": 0.0, "model_version": "", "explain": "no active policy model; legacy score proxy"}
            else:
                try:
                    vector = active["feature_schema"].transform_one(features); bundle = active["model"].get("models", active["model"])
                    reward_model = bundle.get("reward_regressor"); success_model = bundle.get("success_classifier"); risk_model = bundle.get("risk_classifier")
                    reward = float(reward_model.predict([vector])[0]) if reward_model is not None else 0.0
                    success = _prob(success_model, vector) if success_model is not None else 0.5
                    risk = _prob(risk_model, vector) if risk_model is not None else 0.0
                    score = reward * 0.60 + float(success or 0.0) * 0.25 - float(risk or 0.0) * 0.15
                    pred = {"source": "learned_policy_shadow", "expected_reward_delta": reward, "success_probability": float(success or 0.0), "risk_score": float(risk or 0.0), "action_score": float(score), "confidence": float(getattr(self.config, "ml_model_min_confidence", 0.65) or 0.65), "model_version": active.get("model_version", ""), "explain": "policy shadow action score from active model"}
                except Exception as exc:
                    pred = {"source": "no_model_or_dependency_unavailable", "error": str(exc), "expected_reward_delta": 0.0, "success_probability": 0.0, "risk_score": 0.0, "action_score": float((action or {}).get("legacy_score") or 0.0), "confidence": 0.0, "model_version": "", "explain": "policy prediction failed; legacy score proxy"}
            merged = dict(action or {}); merged["prediction"] = pred; merged["action_score"] = pred.get("action_score", 0.0); scored.append(merged)
            safe_audit_prediction(self.audit_logger, task_name="policy", alpha_id=alpha_id, model_version=pred.get("model_version", ""), features=features, prediction=pred, confidence=pred.get("confidence"), final_decision="shadow_score_action", final_source=pred.get("source", "learned_policy_shadow"))
        return scored
