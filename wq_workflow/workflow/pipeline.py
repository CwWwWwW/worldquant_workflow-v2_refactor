from __future__ import annotations

import uuid
from typing import Any

from .context import WorkflowContext
from .result import StepResult
from .steps import DEFAULT_STEP_CLASSES


def has_observe_only_critical_steps(steps: list[Any]) -> bool:
    return any(bool(getattr(step, "is_critical", False)) and bool(getattr(step, "is_observe_only", False)) for step in steps)


def observe_only_critical_step_names(steps: list[Any]) -> list[str]:
    return [
        str(getattr(step, "name", step.__class__.__name__))
        for step in steps
        if bool(getattr(step, "is_critical", False)) and bool(getattr(step, "is_observe_only", False))
    ]


class WorkflowPipeline:
    def __init__(self, app_context: Any, step_classes: list[type] | None = None) -> None:
        self.ctx = app_context
        self.steps = [cls(app_context) for cls in (step_classes or DEFAULT_STEP_CLASSES)]

    def run_one_iteration(self, workflow_context: WorkflowContext | None = None) -> StepResult:
        wf = workflow_context or WorkflowContext(iteration_id=str(uuid.uuid4()))
        logger = getattr(self.ctx, "logger", None)
        mode = getattr(self.ctx, "runtime_status", {}).get("pipeline_mode")
        if mode:
            wf.local_checks["pipeline_mode"] = mode
        for step in self.steps:
            if logger:
                logger.info("[WorkflowPipeline] enter step=%s iteration_id=%s", step.name, wf.iteration_id)
            try:
                result = step.run(wf)
            except Exception as exc:
                wf.errors.append(f"{step.name}: {exc}")
                result = StepResult(ok=False, fatal=True, error=exc, message=str(exc))
            if result.data:
                for key, value in result.data.items():
                    if hasattr(wf, key):
                        setattr(wf, key, value)
            if logger:
                logger.info("[WorkflowPipeline] exit step=%s ok=%s fatal=%s", step.name, result.ok, result.fatal)
            if result.fatal or result.skip_remaining:
                return result
        return StepResult(ok=not wf.errors, data={"workflow_context": wf})
