from __future__ import annotations

from typing import Any

from wq_workflow.learning.ml.prediction_audit import safe_audit_prediction
from wq_workflow.learning.ml.training_utils import flatten_feature_dict


def _prob(model: Any, vector: list[float]) -> float | None:
    try:
        if hasattr(model, "predict_proba"):
            proba = model.predict_proba([vector])[0]
            return float(proba[1] if len(proba) > 1 else proba[0])
        return float(model.predict([vector])[0])
    except Exception:
        return None


class ParentPredictor:
    def __init__(self, *, model_registry: Any, audit_logger: Any | None = None, config: Any | None = None) -> None:
        self.model_registry = model_registry
        self.audit_logger = audit_logger
        self.config = config

    def predict_parent(self, parent: dict[str, Any], *, alpha_id: str = "") -> dict[str, Any]:
        features = flatten_feature_dict(parent or {})
        try:
            active = self.model_registry.load_active_model("parent") if self.model_registry else None
            if not active:
                return {"source": "no_model_or_dependency_unavailable", "expected_child_reward": 0.0, "child_success_probability": 0.0, "child_sc_risk": 0.0, "parent_rank_score": 0.0, "confidence": 0.0, "model_version": "", "explain": "no active parent model"}
            schema = active["feature_schema"]; vector = schema.transform_one(features); bundle = active["model"].get("models", active["model"]) if isinstance(active["model"], dict) else {}
            reward_model = bundle.get("reward_regressor") if isinstance(bundle, dict) else None
            success_model = bundle.get("success_classifier") if isinstance(bundle, dict) else None
            risk_model = bundle.get("sc_risk_classifier") if isinstance(bundle, dict) else None
            reward = float(reward_model.predict([vector])[0]) if reward_model is not None else 0.0
            success = _prob(success_model, vector) if success_model is not None else 0.5
            risk = _prob(risk_model, vector) if risk_model is not None else 0.0
            score = reward * 0.55 + float(success or 0.0) * 0.30 - float(risk or 0.0) * 0.15
            result = {"source": "learned_parent_shadow", "expected_child_reward": reward, "child_success_probability": float(success or 0.0), "child_sc_risk": float(risk or 0.0), "parent_rank_score": float(score), "confidence": float(getattr(self.config, "ml_model_min_confidence", 0.65) or 0.65), "model_version": active.get("model_version", ""), "explain": "parent shadow score from active random forest models"}
            safe_audit_prediction(self.audit_logger, task_name="parent", alpha_id=alpha_id, model_version=result["model_version"], features=features, prediction=result, confidence=result["confidence"], final_decision="shadow_rank_parent", final_source="learned_parent_shadow")
            return result
        except Exception as exc:
            return {"source": "no_model_or_dependency_unavailable", "error": str(exc), "expected_child_reward": 0.0, "child_success_probability": 0.0, "child_sc_risk": 0.0, "parent_rank_score": 0.0, "confidence": 0.0, "model_version": "", "explain": "parent prediction failed"}

    def rank_parents(self, parents: list[dict[str, Any]] | None, *, alpha_id: str = "") -> list[dict[str, Any]]:
        out = []
        for parent in parents or []:
            pred = self.predict_parent(parent, alpha_id=alpha_id)
            merged = dict(parent or {}); merged["prediction"] = pred; merged["parent_rank_score"] = pred.get("parent_rank_score", 0.0); out.append(merged)
        return sorted(out, key=lambda r: float(r.get("parent_rank_score") or 0.0), reverse=True)
