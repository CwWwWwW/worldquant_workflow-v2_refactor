from __future__ import annotations

from typing import Any


class ActionLearningPolicy:
    def __init__(self, *, config: Any, decision_logger: Any | None = None, predictor: Any | None = None, audit_logger: Any | None = None, governance_service: Any | None = None) -> None:
        self.config = config
        self.decision_logger = decision_logger
        self.predictor = predictor
        self.audit_logger = audit_logger
        self.governance_service = governance_service

    def score_actions(self, actions: list[dict[str, Any]] | None = None, *, context: dict[str, Any] | None = None) -> dict[str, float]:
        if self.predictor is not None and getattr(self.config, "enable_policy_model_prediction", True):
            try:
                scored = self.predictor.score_actions(actions or [], context=context, alpha_id=str((context or {}).get("alpha_id", "")))
                return {str(a.get("action_id") or a.get("id") or idx): float(a.get("action_score") or 0.0) for idx, a in enumerate(scored)}
            except Exception:
                pass
        scores: dict[str, float] = {}
        for idx, action in enumerate(actions or []):
            if isinstance(action, dict):
                key = str(action.get("action_id") or action.get("id") or idx)
                scores[key] = float(action.get("legacy_score", 0.0) or 0.0)
        return scores

    def choose_action(self, actions: list[dict[str, Any]] | None = None, *, legacy_action: dict[str, Any] | None = None, context: dict[str, Any] | None = None, workflow_context: Any | None = None, return_decision_id: bool = False) -> Any:
        chosen = legacy_action or ((actions or [None])[0])
        scores = self.score_actions(actions, context=context)
        allow_decision = bool(getattr(self.config, "enable_policy_model_decision", False))
        if allow_decision and self.governance_service is not None:
            try:
                allow_decision = bool(self.governance_service.allow_hard_decision("policy", "mutation_policy", self.config).allowed)
            except Exception:
                allow_decision = False
        elif allow_decision:
            allow_decision = False
        if allow_decision and scores and actions:
            best_key = max(scores, key=lambda k: scores[k])
            chosen = next((a for idx, a in enumerate(actions or []) if str((a or {}).get("action_id") or (a or {}).get("id") or idx) == best_key), chosen)
        decision_id = None
        if self.decision_logger:
            decision_id = self.decision_logger.record(
                decision_type="policy_action",
                alpha_id=str((context or {}).get("alpha_id", "")),
                context=context or {},
                available_actions=actions or [],
                chosen_action=chosen or {},
                action_scores=scores,
                selection_reason="learned_policy_shadow_legacy_default" if self.predictor is not None else "legacy_default_observe_only",
                legacy_score=(scores.get(str((chosen or {}).get("action_id"))) if isinstance(chosen, dict) else None),
                model_score=max(scores.values()) if scores else None,
            )
        if self.audit_logger:
            try:
                self.audit_logger.record(task_name="policy", alpha_id=str((context or {}).get("alpha_id", "")), features=context or {}, prediction={"action_scores": scores, "explain": "policy shadow scores; legacy action kept by default"}, final_decision="legacy_policy", final_source="legacy_policy", raw_payload={"available_actions": actions or [], "chosen_action": chosen or {}})
            except Exception:
                pass
        if workflow_context is not None:
            if decision_id:
                try:
                    setattr(workflow_context, "policy_decision_id", decision_id)
                    workflow_context.decisions.append({"decision_id": decision_id, "decision_type": "policy_action", "alpha_id": str((context or {}).get("alpha_id", "")), "context": context or {}, "available_actions": actions or [], "chosen_action": chosen or {}, "action_scores": scores, "selection_reason": "learned_policy_shadow_legacy_default" if self.predictor is not None else "legacy_default_observe_only"})
                except Exception:
                    pass
            try:
                workflow_context.policy_shadow_scores = scores
            except Exception:
                pass
        return (chosen, decision_id) if return_decision_id else chosen

    def record_outcome(self, **kwargs: Any) -> None:
        return None
