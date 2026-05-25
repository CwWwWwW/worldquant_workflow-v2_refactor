from __future__ import annotations

import hashlib
import uuid
from pathlib import Path
from typing import Any

from wq_workflow.data.json_utils import to_jsonable

from .schema import DecisionAction, DecisionSnapshot, utc_now_iso


class DecisionSnapshotBuilder:
    def build_action(
        self,
        action_type: str,
        name: str,
        source: str = "unknown",
        score: float | None = None,
        rank: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> DecisionAction:
        base = f"{action_type}:{name}:{source}"
        digest = hashlib.sha256(base.encode("utf-8", errors="replace")).hexdigest()[:12]
        return DecisionAction(
            action_id=f"action:{digest}",
            action_type=str(action_type or "unknown"),
            name=str(name or action_type or "unknown"),
            source=str(source or "unknown"),
            score=score,
            rank=rank,
            metadata=metadata or {},
        )

    def normalize_actions(self, actions: Any) -> list[DecisionAction]:
        if actions is None:
            return []
        if isinstance(actions, DecisionAction):
            return [actions]
        if isinstance(actions, (str, dict)):
            return [DecisionAction.from_dict(actions)]
        if isinstance(actions, (list, tuple, set)):
            result: list[DecisionAction] = []
            for item in actions:
                try:
                    result.append(DecisionAction.from_dict(item))
                except Exception:
                    result.append(DecisionAction.from_dict(str(item)))
            return result
        return [DecisionAction.from_dict(str(actions))]

    def stable_decision_id(self, decision_type: str, context: Any) -> str:
        data = context if isinstance(context, dict) else {}
        explicit = data.get("decision_id")
        if explicit:
            return str(explicit)
        parts = [
            str(decision_type or "unknown"),
            str(data.get("workflow_run_id") or data.get("run_id") or ""),
            str(data.get("iteration") or data.get("iteration_id") or ""),
            str(data.get("alpha_id") or ""),
            str(data.get("experiment_id") or ""),
            str(data.get("arm_id") or ""),
            str(data.get("budget_plan_id") or ""),
            str(data.get("expression_hash") or data.get("template_name") or data.get("mutation_type") or ""),
        ]
        seed = "|".join(parts)
        if seed.strip("|"):
            digest = hashlib.sha256(seed.encode("utf-8", errors="replace")).hexdigest()[:24]
        else:
            digest = uuid.uuid4().hex[:24]
        return f"decision:{str(decision_type or 'unknown')}:{digest}"

    def extract_common_context(self, context: Any) -> dict[str, Any]:
        data = context if isinstance(context, dict) else {}
        nested = data.get("context") if isinstance(data.get("context"), dict) else {}
        merged = dict(nested)
        for key in (
            "workflow_run_id",
            "run_id",
            "iteration",
            "iteration_id",
            "alpha_id",
            "experiment_id",
            "arm_id",
            "budget_plan_id",
            "template_name",
            "template_family",
            "operator_family",
            "mutation_type",
            "field_family",
            "behavior_family",
            "expression_hash",
            "candidate_source",
            "assigned_by",
        ):
            if key in data and key not in merged:
                merged[key] = data.get(key)
        return _clean_dict(merged)

    def build_snapshot(self, decision_type: str, context: Any) -> DecisionSnapshot:
        data = context if isinstance(context, dict) else {}
        now = utc_now_iso()
        return DecisionSnapshot(
            decision_id=self.stable_decision_id(decision_type, data),
            decision_type=str(decision_type or data.get("decision_type") or "unknown"),
            workflow_run_id=_nullable_text(data.get("workflow_run_id") or data.get("run_id")),
            iteration=_nullable_int(data.get("iteration") if data.get("iteration") is not None else data.get("iteration_id")),
            alpha_id=_nullable_text(data.get("alpha_id")),
            experiment_id=_nullable_text(data.get("experiment_id")),
            arm_id=_nullable_text(data.get("arm_id")),
            budget_plan_id=_nullable_text(data.get("budget_plan_id")),
            available_actions=self.normalize_actions(data.get("available_actions")),
            chosen_action=_maybe_action(data.get("chosen_action")),
            legacy_choice=_maybe_action(data.get("legacy_choice")),
            model_choice=_maybe_action(data.get("model_choice")),
            experiment_choice=_maybe_action(data.get("experiment_choice")),
            governance_decision=_nullable_text(data.get("governance_decision")),
            features=_clean_dict(data.get("features") or {}),
            scores=_clean_dict(data.get("scores") or data.get("action_scores") or {}),
            context=self.extract_common_context(data),
            actual_result=_clean_dict(data.get("actual_result") or {}) if data.get("actual_result") is not None else None,
            reward=_nullable_float(data.get("reward")),
            platform_sc_status=_nullable_text(data.get("platform_sc_status")),
            platform_sc_abs_max=_nullable_float(data.get("platform_sc_abs_max")),
            success=_nullable_bool(data.get("success")),
            quality_passed=_nullable_bool(data.get("quality_passed")),
            created_at=str(data.get("created_at") or now),
            updated_at=str(data.get("updated_at") or now),
            raw_payload=_clean_dict(data.get("raw_payload") or data),
        )


class DecisionSnapshotLogger:
    """Compatibility wrapper for the pre-5A logger API."""

    def __init__(self, *, storage: Any | None = None, db_path: str | Path | None = None, repository: Any | None = None, logger: Any | None = None) -> None:
        self.storage = storage
        self.logger = logger
        if repository is not None and hasattr(repository, "insert_decision_snapshot"):
            self.legacy_repository = repository
            self.service = None
        elif repository is None:
            from wq_workflow.data.repositories import DecisionRepository

            self.legacy_repository = DecisionRepository(storage=storage, db_path=db_path)
            self.service = None
        else:
            self.legacy_repository = None
            from .service import DecisionSnapshotService

            self.service = DecisionSnapshotService(repository=repository, storage=storage, db_path=db_path, logger=logger)

    def _representation_summary(self, context: dict[str, Any], raw_payload: dict[str, Any]) -> dict[str, Any]:
        try:
            from wq_workflow.alpha.representation.features import build_alpha_representation

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
            return {}
        except Exception:
            try:
                from wq_workflow.alpha.representation.features import build_alpha_representation

                return build_alpha_representation("").summary()
            except Exception:
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
        actions = [] if available_actions is None else (available_actions if isinstance(available_actions, list) else [available_actions])
        safe_context = self._safe_context(context, raw_payload)
        try:
            if self.legacy_repository is not None:
                return self.legacy_repository.insert_decision_snapshot(
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
            if self.service is not None:
                snapshot = self.service.record_decision(
                    _normalize_decision_type(decision_type),
                    {
                        "decision_id": decision_id,
                        "alpha_id": alpha_id,
                        "context": safe_context,
                        "available_actions": actions,
                        "chosen_action": chosen_action or {},
                        "scores": action_scores or {},
                        "legacy_choice": {"action_type": "legacy", "name": "legacy", "source": "legacy", "score": legacy_score} if legacy_score is not None else None,
                        "model_choice": {"action_type": "ml", "name": "model", "source": "ml", "score": model_score, "metadata": {"model_version": model_version}} if model_score is not None or model_version else None,
                        "raw_payload": {"selection_reason": selection_reason, "propensity": propensity, **(raw_payload or {})},
                    },
                )
                return snapshot.decision_id if snapshot is not None else decision_id
        except Exception as exc:
            _warn(self.logger, "decision snapshot write failed: %s", exc)
        return decision_id


class DecisionOutcomeRecorder:
    """Compatibility wrapper for the pre-5A outcome API."""

    def __init__(self, *, storage: Any | None = None, db_path: str | Path | None = None, repository: Any | None = None, logger: Any | None = None) -> None:
        self.logger = logger
        if repository is not None and hasattr(repository, "insert_decision_outcome"):
            self.legacy_repository = repository
            self.service = None
        elif repository is None:
            from wq_workflow.data.repositories import DecisionRepository

            self.legacy_repository = DecisionRepository(storage=storage, db_path=db_path)
            self.service = None
        else:
            self.legacy_repository = None
            from .service import DecisionSnapshotService

            self.service = DecisionSnapshotService(repository=repository, storage=storage, db_path=db_path, logger=logger)

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
            if self.legacy_repository is not None:
                return self.legacy_repository.insert_decision_outcome(
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
            if self.service is not None:
                outcomes = self.service.record_outcome(
                    alpha_id,
                    {
                        "decision_id": decision_id,
                        "reward": reward,
                        "reward_delta": reward_delta,
                        "success": success,
                        "failure_type": failure_type,
                        "platform_sc_abs_max": platform_sc_abs_max,
                        "raw_payload": {"decision_type": decision_type, "metrics": metrics or {}, **(raw_payload or {})},
                    },
                )
                return outcomes[0].outcome_id if outcomes else None
        except Exception as exc:
            _warn(self.logger, "decision outcome write failed: %s", exc)
        return None


def _normalize_decision_type(value: str) -> str:
    mapping = {"parent": "parent_selection", "policy_action": "mutation_policy", "simulator_decision": "simulator_skip"}
    return mapping.get(str(value or "unknown"), str(value or "unknown"))


def _maybe_action(value: Any) -> DecisionAction | None:
    if value is None or value == "":
        return None
    return DecisionAction.from_dict(value)


def _nullable_text(value: Any) -> str | None:
    if value is None or value == "":
        return None
    return str(value)


def _nullable_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except Exception:
        return None


def _nullable_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        number = float(value)
        return number if number == number and number not in {float("inf"), float("-inf")} else None
    except Exception:
        return None


def _nullable_bool(value: Any) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on", "pass", "passed", "success"}:
        return True
    if text in {"0", "false", "no", "n", "off", "fail", "failed", "failure"}:
        return False
    return None


def _clean_dict(value: Any) -> dict[str, Any]:
    cleaned = to_jsonable(value if isinstance(value, dict) else {})
    return cleaned if isinstance(cleaned, dict) else {}


def _warn(logger: Any | None, message: str, exc: Exception) -> None:
    try:
        if logger is not None:
            logger.warning(message, exc)
    except Exception:
        pass
