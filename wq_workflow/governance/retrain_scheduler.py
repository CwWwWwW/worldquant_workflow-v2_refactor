from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from .lifecycle import ModelLifecycleStatus, expires_at_iso, is_expired
from .schema import GovernanceCheckResult


class RetrainScheduler:
    def __init__(self, config: Any | None = None, registry_adapter: Any | None = None, sample_quality_checker: Any | None = None, event_logger: Any | None = None, trainers: dict[str, Any] | None = None, logger: Any | None = None) -> None:
        self.config = config
        self.registry_adapter = registry_adapter
        self.sample_quality_checker = sample_quality_checker
        self.event_logger = event_logger
        self.trainers = trainers or {}
        self.logger = logger
        self._last_retrain: dict[str, datetime] = {}

    def _event(self, **kwargs: Any) -> None:
        try:
            if self.event_logger is not None:
                self.event_logger.record(**kwargs)
        except Exception:
            pass

    def should_retrain(self, task_name: str, *, metadata: dict[str, Any] | None = None, sample_count: int | None = None, drift_detected: bool = False, online_performance_drop: bool = False, registry_inconsistent: bool = False, manual: bool = False) -> GovernanceCheckResult:
        task = str(task_name or "")
        if not bool(getattr(self.config, "enable_auto_retrain", True)) and not manual:
            return GovernanceCheckResult(ok=True, task_name=task, recommended_action="keep_shadow", reason="auto_retrain_disabled")
        min_interval = int(getattr(self.config, "ml_min_retrain_interval_minutes", 30) or 30)
        last = self._last_retrain.get(task)
        if last and datetime.now(UTC) - last < timedelta(minutes=min_interval) and not manual:
            return GovernanceCheckResult(ok=True, task_name=task, recommended_action="keep_shadow", reason="min_interval_not_elapsed")
        every = int(getattr(self.config, "ml_retrain_every_samples", 50) or 50)
        metadata = metadata or (self.registry_adapter.get_active_metadata(task) if self.registry_adapter else None) or {}
        if not metadata:
            return GovernanceCheckResult(ok=True, task_name=task, recommended_action="retrain", reason="no_active_model")
        raw = metadata.get("raw_payload") if isinstance(metadata.get("raw_payload"), dict) else {}
        expires_at = raw.get("expires_at") or metadata.get("expires_at")
        if expires_at and is_expired(expires_at):
            return GovernanceCheckResult(ok=True, task_name=task, recommended_action="retrain", reason="model_expired")
        if drift_detected or online_performance_drop or registry_inconsistent or manual:
            return GovernanceCheckResult(ok=True, task_name=task, recommended_action="retrain", reason="triggered")
        if sample_count is not None and sample_count >= every:
            return GovernanceCheckResult(ok=True, task_name=task, recommended_action="retrain", reason="sample_threshold_reached")
        return GovernanceCheckResult(ok=True, task_name=task, recommended_action="keep_active", reason="no_retrain_needed")

    def run_retrain(self, task_name: str, *, samples: list[dict[str, Any]] | None = None, trainer: Any | None = None, manual: bool = False) -> GovernanceCheckResult:
        task = str(task_name or "")
        self._event(task_name=task, event_type="auto_retrain_started", severity="info", message="auto retrain started", action_taken="retrain")
        try:
            if samples is not None and self.sample_quality_checker is not None:
                quality = self.sample_quality_checker.check(task, samples)
                if not quality.ok:
                    return GovernanceCheckResult(ok=False, task_name=task, recommended_action="keep_shadow", reason="sample_quality_failed", warnings=quality.warnings + quality.errors, raw_payload={"quality": quality.to_dict()})
            trainer = trainer or self.trainers.get(task)
            if trainer is None:
                return GovernanceCheckResult(ok=False, task_name=task, recommended_action="keep_shadow", reason="trainer_unavailable")
            fn = getattr(trainer, "train", None) or getattr(trainer, "run", None) or trainer
            result = fn() if callable(fn) else {"status": "skipped", "reason": "trainer_not_callable"}
            status = "shadow"
            version = None
            if isinstance(result, dict):
                version = result.get("model_version")
                if result.get("status") in {"failed", "error"} or result.get("ok") is False:
                    raise RuntimeError(str(result.get("reason") or result.get("error") or "trainer_failed"))
            if self.registry_adapter is not None and version:
                self.registry_adapter.mark_lifecycle(task, str(version), status, reason="auto_retrain_success_shadow")
            self._last_retrain[task] = datetime.now(UTC)
            self._event(task_name=task, model_version=version, event_type="auto_retrain_succeeded", severity="info", message="auto retrain succeeded", action_taken="keep_shadow", raw_payload={"result": result})
            return GovernanceCheckResult(ok=True, task_name=task, recommended_action="keep_shadow", reason="retrain_succeeded", raw_payload={"result": result})
        except Exception as exc:
            self._event(task_name=task, event_type="auto_retrain_failed", severity="warning", message=str(exc), action_taken="keep_previous_model")
            if bool(getattr(self.config, "ml_auto_disable_on_retrain_failure", True)) and self.registry_adapter is not None:
                # Keep old model active but force legacy/hard-decision-off through governance result.
                pass
            return GovernanceCheckResult(ok=False, task_name=task, recommended_action="force_legacy", reason=f"retrain_failed:{exc}")
