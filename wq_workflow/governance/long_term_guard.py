from __future__ import annotations

from typing import Any

from .lifecycle import ModelLifecycleStatus, is_expired, utc_now_iso
from .schema import GovernanceCheckResult, TaskGovernanceState

TASKS = ("sc", "parent", "policy", "simulator", "outcome", "insight")


class LongTermGuard:
    def __init__(self, registry_adapter: Any | None = None, online_evaluator: Any | None = None, retrain_scheduler: Any | None = None, status_writer: Any | None = None, event_logger: Any | None = None, config: Any | None = None, logger: Any | None = None) -> None:
        self.registry_adapter = registry_adapter
        self.online_evaluator = online_evaluator
        self.retrain_scheduler = retrain_scheduler
        self.status_writer = status_writer
        self.event_logger = event_logger
        self.config = config
        self.logger = logger

    def _event(self, **kwargs: Any) -> None:
        try:
            if self.event_logger is not None:
                self.event_logger.record(**kwargs)
        except Exception:
            pass

    def check_task(self, task_name: str) -> GovernanceCheckResult:
        task = str(task_name or "")
        try:
            meta = self.registry_adapter.get_active_metadata(task) if self.registry_adapter is not None else None
            if not meta:
                result = GovernanceCheckResult(ok=True, task_name=task, recommended_action="force_legacy", reason="no_active_model")
                self._write_state(task, None, "shadow", 0.0, True, {}, {"reason": result.reason})
                self._event(task_name=task, event_type="fallback_to_legacy", severity="info", message="no active model", action_taken="force_legacy")
                return result
            registry = self.check_registry(task)
            if not registry.ok:
                repair = self.registry_adapter.repair_registry(task) if self.registry_adapter is not None else {"ok": False}
                if not repair.get("ok", False) and self.registry_adapter is not None:
                    self.registry_adapter.disable_active_model(task, reason="registry_repair_failed")
                    self._event(task_name=task, model_version=meta.get("model_version"), event_type="model_disabled", severity="warning", message="registry repair failed", action_taken="disable_model", raw_payload={"repair": repair})
                    result = GovernanceCheckResult(ok=False, task_name=task, recommended_action="force_legacy", reason="registry_inconsistent_repair_failed", raw_payload={"repair": repair})
                    self._write_state(task, meta.get("model_version"), "disabled", 0.0, True, {}, {"reason": result.reason})
                    return result
            freshness = self.check_model_freshness(task, meta)
            if not freshness.ok:
                action = "retrain"
                result = self.apply_model_action(task, str(meta.get("model_version") or ""), action, {"reason": freshness.reason})
                return result
            online = self.check_online_performance(task, str(meta.get("model_version") or ""))
            action = self.decide_model_action(task, meta, freshness, online)
            return self.apply_model_action(task, str(meta.get("model_version") or ""), action, {"online_eval": online.raw_payload, "reason": online.reason})
        except Exception as exc:
            self._event(task_name=task, event_type="governance_check_failed", severity="warning", message=str(exc), action_taken="force_legacy")
            return GovernanceCheckResult(ok=False, task_name=task, recommended_action="force_legacy", reason=f"guard_exception:{exc}")

    def check_all_tasks(self) -> dict[str, GovernanceCheckResult]:
        return {task: self.check_task(task) for task in TASKS}

    def check_model_freshness(self, task_name: str, metadata: dict[str, Any]) -> GovernanceCheckResult:
        raw = metadata.get("raw_payload") if isinstance(metadata.get("raw_payload"), dict) else {}
        expires_at = raw.get("expires_at") or metadata.get("expires_at")
        if expires_at and is_expired(expires_at):
            self._event(task_name=task_name, model_version=metadata.get("model_version"), event_type="model_expired", severity="warning", message="model expired", action_taken="retrain")
            return GovernanceCheckResult(ok=False, task_name=task_name, recommended_action="retrain", reason="model_expired")
        return GovernanceCheckResult(ok=True, task_name=task_name, recommended_action="keep_active", reason="fresh")

    def check_registry(self, task_name: str) -> GovernanceCheckResult:
        result = self.registry_adapter.check_registry_consistency(task_name) if self.registry_adapter is not None else {"ok": False, "issues": [{"issue": "registry_adapter_unavailable"}]}
        if not result.get("ok", False):
            self._event(task_name=task_name, event_type="registry_inconsistent", severity="warning", message="registry inconsistent", action_taken="repair", raw_payload=result)
            return GovernanceCheckResult(ok=False, task_name=task_name, recommended_action="force_legacy", reason="registry_inconsistent", raw_payload=result)
        return GovernanceCheckResult(ok=True, task_name=task_name, recommended_action="keep_active", reason="registry_ok")

    def check_online_performance(self, task_name: str, model_version: str) -> GovernanceCheckResult:
        if self.online_evaluator is None or not bool(getattr(self.config, "enable_online_model_evaluation", True)):
            return GovernanceCheckResult(ok=True, task_name=task_name, recommended_action="keep_active", reason="online_eval_disabled")
        result = self.online_evaluator.evaluate_task(task_name, model_version)
        ok = result.recommended_action not in {"disable_model", "rollback", "force_legacy"}
        return GovernanceCheckResult(ok=ok, task_name=task_name, recommended_action=result.recommended_action, reason="online_eval", raw_payload=result.to_dict())

    def decide_model_action(self, task_name: str, metadata: dict[str, Any], freshness: GovernanceCheckResult, online_eval: GovernanceCheckResult) -> str:
        if not freshness.ok:
            return freshness.recommended_action
        if online_eval.recommended_action in {"reduce_weight", "retrain", "rollback", "disable_model", "force_legacy", "keep_shadow", "keep_active"}:
            return online_eval.recommended_action
        return "keep_active"

    def apply_model_action(self, task_name: str, model_version: str, action: str, payload: dict[str, Any] | None = None) -> GovernanceCheckResult:
        payload = payload or {}
        try:
            if action == "reduce_weight" and self.registry_adapter is not None:
                self.registry_adapter.update_model_weight(task_name, model_version, 0.05)
                event_type = "model_weight_reduced"
                fallback = False
                status = "degraded"
                weight = 0.05
            elif action == "disable_model" and self.registry_adapter is not None:
                self.registry_adapter.disable_active_model(task_name, reason=str(payload.get("reason") or "online_eval_disable"))
                event_type = "model_disabled"
                fallback = True
                status = "disabled"
                weight = 0.0
            elif action == "rollback" and self.registry_adapter is not None:
                ok = self.registry_adapter.rollback_to_previous_active(task_name)
                event_type = "model_rolled_back" if ok else "fallback_to_legacy"
                fallback = not ok
                status = "rolled_back" if ok else "disabled"
                weight = 0.0 if not ok else 0.25
            elif action == "retrain" and self.retrain_scheduler is not None:
                retrain_result = self.retrain_scheduler.run_retrain(task_name)
                event_type = "auto_retrain_succeeded" if retrain_result.ok else "auto_retrain_failed"
                fallback = True
                status = "shadow"
                weight = 0.0
                payload["retrain_result"] = retrain_result.to_dict()
            elif action == "force_legacy":
                event_type = "fallback_to_legacy"
                fallback = True
                status = "shadow"
                weight = 0.0
            elif action == "keep_shadow":
                event_type = "model_shadow_only"
                fallback = True
                status = "shadow"
                weight = 0.0
            else:
                event_type = "governance_startup_check"
                fallback = False
                status = "active"
                weight = float((payload.get("online_eval") or {}).get("model_weight") or 1.0)
            self._event(task_name=task_name, model_version=model_version, event_type=event_type, severity="warning" if fallback else "info", message=f"governance action {action}", action_taken=action, raw_payload=payload)
            self._write_state(task_name, model_version, status, weight, fallback, payload.get("online_eval") if isinstance(payload.get("online_eval"), dict) else {}, {"event_type": event_type, "action": action})
            return GovernanceCheckResult(ok=not (action in {"disable_model", "force_legacy"}), task_name=task_name, recommended_action=action, reason=f"action_applied:{action}", raw_payload=payload)
        except Exception as exc:
            self._event(task_name=task_name, model_version=model_version, event_type="governance_action_failed", severity="warning", message=str(exc), action_taken="force_legacy")
            return GovernanceCheckResult(ok=False, task_name=task_name, recommended_action="force_legacy", reason=f"action_failed:{exc}")

    def _write_state(self, task: str, version: str | None, status: str, weight: float, fallback: bool, online: dict[str, Any], event: dict[str, Any]) -> None:
        try:
            if self.status_writer is not None:
                self.status_writer.write_task(TaskGovernanceState(task_name=task, active_model_version=version, lifecycle_status=status, model_weight=weight, fallback_active=fallback, last_online_eval=online, last_event=event, updated_at=utc_now_iso()))
        except Exception:
            pass
