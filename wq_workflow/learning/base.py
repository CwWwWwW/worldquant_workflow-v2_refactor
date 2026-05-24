from __future__ import annotations

from typing import Any

from wq_workflow.core_types import ServiceResult


class LearningTaskService:
    task_name = "base"

    def record_sample(self, context: Any) -> ServiceResult:
        return ServiceResult(ok=True, data=None, source=f"learning.{self.task_name}.record_sample")

    def maybe_train(self) -> ServiceResult:
        return ServiceResult(ok=True, data=None, source=f"learning.{self.task_name}.maybe_train")

    def predict(self, features: Any) -> ServiceResult:
        return ServiceResult(ok=False, data=None, error="not_implemented", source=f"learning.{self.task_name}.predict")

    def audit_prediction(self, *args: Any, **kwargs: Any) -> ServiceResult:
        return ServiceResult(ok=True, data=None, source=f"learning.{self.task_name}.audit_prediction")
