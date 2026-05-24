from __future__ import annotations

from dataclasses import replace
from typing import Any


HARD_DECISION_FLAGS: tuple[tuple[str, str], ...] = (
    ("enable_parent_model_decision", "parent"),
    ("enable_policy_model_decision", "policy"),
    ("enable_simulator_model_skip", "simulator"),
    ("enable_sc_model_fallback", "sc"),
)


def _copy_config(config: Any) -> Any:
    try:
        return replace(config)
    except Exception:
        import copy

        return copy.copy(config)


def _set(config: Any, name: str, value: Any) -> None:
    try:
        setattr(config, name, value)
    except Exception:
        pass


def _has_active_model(registry: Any, task_name: str) -> bool:
    if registry is None:
        return False
    try:
        return bool(registry.load_active_model(task_name))
    except Exception:
        return False


def apply_config_safety_gate(config: Any, *, model_registry: Any | None = None, governance_service: Any | None = None, step_classes: list[type] | None = None, logger: Any | None = None) -> dict[str, Any]:
    """Return an effective config with unsafe v1.2.7 switches disabled.

    The source config file/object is not modified.
    """
    from wq_workflow.workflow.pipeline import has_observe_only_critical_steps, observe_only_critical_step_names
    from wq_workflow.workflow.steps import DEFAULT_STEP_CLASSES

    effective = _copy_config(config)
    warnings: list[str] = []
    disabled_flags: list[str] = []
    unsafe_allowed = bool(getattr(config, "force_enable_unsafe_ml_decisions", False))

    steps = [cls(None) for cls in (step_classes or DEFAULT_STEP_CLASSES)]
    if bool(getattr(effective, "enable_refactored_pipeline", False)) and has_observe_only_critical_steps(steps):
        names = observe_only_critical_step_names(steps)
        if not bool(getattr(effective, "allow_observe_only_pipeline", False)):
            _set(effective, "enable_refactored_pipeline", False)
            disabled_flags.append("enable_refactored_pipeline")
            warnings.append(f"refactored pipeline disabled because critical steps are observe-only: {names}")
        else:
            warnings.append(f"UNSAFE allow_observe_only_pipeline=true with observe-only critical steps: {names}")

    if governance_service is None and bool(getattr(config, "enable_learning_governance", True)):
        try:
            from wq_workflow.governance.service import LearningGovernanceService

            governance_service = LearningGovernanceService(config=effective, model_registry=model_registry, logger=logger)
        except Exception as exc:
            warnings.append(f"governance service unavailable: {exc}")

    for flag, task in HARD_DECISION_FLAGS:
        if not bool(getattr(effective, flag, False)):
            continue
        decision = None
        if governance_service is not None:
            try:
                decision_type = {
                    "sc": "sc_fallback",
                    "parent": "parent_selection",
                    "policy": "mutation_policy",
                    "simulator": "simulator_skip",
                }.get(task, task)
                decision = governance_service.allow_hard_decision(task, decision_type, effective)
            except Exception as exc:
                warnings.append(f"governance gate failed for {flag}: {exc}")
        unsafe_by_governance = decision is not None and not bool(getattr(decision, "allowed", False))
        if bool(getattr(effective, flag, False)) and (unsafe_by_governance or not _has_active_model(model_registry, task)):
            if unsafe_allowed:
                reason = getattr(decision, "reason", f"without active {task} model") if decision is not None else f"without active {task} model"
                warnings.append(f"UNSAFE {flag}=true {reason}")
                continue
            _set(effective, flag, False)
            disabled_flags.append(flag)
            reason = getattr(decision, "reason", "active model is unavailable") if decision is not None else f"active {task} model is unavailable"
            warnings.append(f"{flag} disabled because {reason}")

    for message in warnings:
        try:
            if logger is not None:
                logger.warning("config safety gate: %s", message)
        except Exception:
            pass

    return {"effective_config": effective, "warnings": warnings, "disabled_flags": disabled_flags}
