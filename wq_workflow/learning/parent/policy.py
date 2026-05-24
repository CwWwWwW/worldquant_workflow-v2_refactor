from __future__ import annotations

from typing import Any


class ParentLearningPolicy:
    def __init__(self, *, config: Any, decision_logger: Any | None = None, legacy_selector: Any | None = None, predictor: Any | None = None, audit_logger: Any | None = None, governance_service: Any | None = None) -> None:
        self.config = config
        self.decision_logger = decision_logger
        self.legacy_selector = legacy_selector
        self.predictor = predictor
        self.audit_logger = audit_logger
        self.governance_service = governance_service

    def can_decide(self) -> bool:
        if not bool(getattr(self.config, "enable_parent_model_decision", False)):
            return False
        if self.governance_service is None:
            return False
        try:
            return bool(self.governance_service.allow_hard_decision("parent", "parent_selection", self.config).allowed)
        except Exception:
            return False

    def shadow_rank(self, available_parents: list[dict[str, Any]] | None = None, *, context: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        alpha_id = str((context or {}).get("alpha_id", ""))
        if self.predictor is None or not getattr(self.config, "enable_parent_model_prediction", True):
            return []
        try:
            return self.predictor.rank_parents(available_parents or [], alpha_id=alpha_id)
        except Exception:
            return []

    def select_parent(self, available_parents: list[dict[str, Any]] | None = None, *, context: dict[str, Any] | None = None, workflow_context: Any | None = None, return_decision_id: bool = False) -> Any:
        available = available_parents or []
        shadow = self.shadow_rank(available, context=context)
        chosen = self.legacy_selector(available) if callable(self.legacy_selector) else (available[0] if available else None)
        if self.can_decide() and shadow:
            # Fourth phase keeps legacy as default; this branch is config-gated and still falls back safely.
            chosen = shadow[0]
        scores = {str((p or {}).get("alpha_id") or (p or {}).get("id") or idx): float((p or {}).get("parent_rank_score") or 0.0) for idx, p in enumerate(shadow or [])}
        decision_id = None
        if self.decision_logger:
            decision_id = self.decision_logger.record(
                decision_type="parent_selection",
                alpha_id=str((context or {}).get("alpha_id", "")),
                context=context or {},
                available_actions=available,
                chosen_action=chosen or {},
                action_scores=scores,
                selection_reason="learned_parent_shadow_legacy_default" if shadow else "legacy_default_observe_only",
                model_score=max(scores.values()) if scores else None,
            )
        if self.audit_logger:
            try:
                self.audit_logger.record(task_name="parent", alpha_id=str((context or {}).get("alpha_id", "")), features=context or {}, prediction={"shadow_rankings": shadow, "explain": "parent policy shadow ranking; legacy decision kept"}, confidence=None, final_decision="legacy_parent", final_source="legacy_parent", raw_payload={"available_parents": available})
            except Exception:
                pass
        if workflow_context is not None:
            if decision_id:
                try:
                    setattr(workflow_context, "parent_decision_id", decision_id)
                    workflow_context.decisions.append({"decision_id": decision_id, "decision_type": "parent_selection", "alpha_id": str((context or {}).get("alpha_id", "")), "context": context or {}, "available_actions": available, "chosen_action": chosen or {}, "action_scores": scores, "selection_reason": "learned_parent_shadow_legacy_default" if shadow else "legacy_default_observe_only"})
                except Exception:
                    pass
            try:
                workflow_context.parent_shadow_ranking = shadow
            except Exception:
                pass
        return (chosen, decision_id) if return_decision_id else chosen
