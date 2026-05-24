from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from wq_workflow.alpha.representation.features import build_alpha_representation


class DecisionSnapshotLogger:
    def __init__(self, *, storage: Any | None = None, db_path: str | Path | None = None, repository: Any | None = None, logger: Any | None = None) -> None:
        self.storage = storage
        self.logger = logger
        if repository is not None:
            self.repository = repository
        else:
            from wq_workflow.data.repositories import DecisionRepository

            self.repository = DecisionRepository(storage=storage, db_path=db_path)

    def _representation_summary(self, context: dict[str, Any], raw_payload: dict[str, Any]) -> dict[str, Any]:
        try:
            rep = context.get("alpha_representation") if isinstance(context, dict) else None
            if rep is None and isinstance(raw_payload, dict):
                rep = raw_payload.get("alpha_representation")
            wf = raw_payload.get("workflow_context") if isinstance(raw_payload, dict) else None
            if rep is None and wf is not None:
                rep = getattr(wf, "alpha_representation", None)
            if rep is not None and hasattr(rep, "summary"):
                return rep.summary()

            expression = ""
            for source in (context, raw_payload):
                if isinstance(source, dict):
                    expression = str(source.get("expression") or source.get("code") or "")
                    if expression:
                        break
                    candidate = source.get("candidate")
                    if isinstance(candidate, dict):
                        expression = str(candidate.get("expression") or candidate.get("code") or "")
                        if expression:
                            break
            if not expression and wf is not None:
                candidate = getattr(wf, "candidate", {}) or {}
                if isinstance(candidate, dict):
                    expression = str(candidate.get("expression") or candidate.get("code") or "")
            if expression:
                return build_alpha_representation(expression).summary()
        except Exception:
            try:
                return build_alpha_representation("").summary()
            except Exception:
                return {}
        return {}

    def _safe_context(self, context: dict[str, Any] | None, raw_payload: dict[str, Any] | None) -> dict[str, Any]:
        full_context = dict(context or {})
        summary = self._representation_summary(full_context, raw_payload or {})
        if summary:
            full_context["alpha_representation"] = summary
        return full_context

    def record(
        self,
        *,
        decision_type: str,
        alpha_id: str = "",
        context: dict[str, Any] | None = None,
        available_actions: list[Any] | dict[str, Any] | None = None,
        chosen_action: dict[str, Any] | Any | None = None,
        action_scores: dict[str, Any] | None = None,
        selection_reason: str = "",
        legacy_score: float | None = None,
        model_score: float | None = None,
        propensity: float | None = None,
        model_version: str = "",
        raw_payload: dict[str, Any] | None = None,
    ) -> str:
        decision_id = uuid.uuid4().hex
        if available_actions is None:
            actions: list[Any] = []
        elif isinstance(available_actions, list):
            actions = available_actions
        else:
            actions = [available_actions]
        try:
            safe_context = self._safe_context(context, raw_payload)
            return self.repository.insert_decision_snapshot(
                decision_id=decision_id,
                decision_type=decision_type,
                alpha_id=alpha_id,
                context=safe_context,
                available_actions=actions,
                chosen_action=chosen_action or {},
                action_scores=action_scores or {},
                selection_reason=selection_reason,
                legacy_score=legacy_score,
                model_score=model_score,
                propensity=propensity,
                model_version=model_version or "",
                raw_payload=raw_payload or {},
            )
        except Exception as exc:
            try:
                if self.logger is not None:
                    self.logger.warning("decision snapshot write failed: %s", exc)
            except Exception:
                pass
            return decision_id


class DecisionOutcomeRecorder:
    def __init__(self, *, storage: Any | None = None, db_path: str | Path | None = None, repository: Any | None = None, logger: Any | None = None) -> None:
        self.logger = logger
        if repository is not None:
            self.repository = repository
        else:
            from wq_workflow.data.repositories import DecisionRepository

            self.repository = DecisionRepository(storage=storage, db_path=db_path)

    def record_outcome(
        self,
        *,
        decision_id: str,
        decision_type: str,
        alpha_id: str = "",
        reward: float | None = None,
        reward_delta: float | None = None,
        success: bool | int | None = None,
        failure_type: str = "",
        platform_sc_abs_max: float | None = None,
        metrics: dict[str, Any] | None = None,
        raw_payload: dict[str, Any] | None = None,
    ) -> str | None:
        try:
            return self.repository.insert_decision_outcome(
                decision_id=decision_id,
                decision_type=decision_type,
                alpha_id=alpha_id,
                reward=reward,
                reward_delta=reward_delta,
                success=success,
                failure_type=failure_type,
                platform_sc_abs_max=platform_sc_abs_max,
                metrics=metrics or {},
                raw_payload=raw_payload or {},
            )
        except Exception as exc:
            try:
                if self.logger is not None:
                    self.logger.warning("decision outcome write failed: %s", exc)
            except Exception:
                pass
            return None
