from __future__ import annotations

from typing import Any

from wq_workflow.learning.ml.evaluation import build_evaluation_report, regression_metrics


class SCEvaluator:
    def __init__(self, *, config: Any | None = None) -> None:
        self.config = config

    def evaluate(self, y_true: Any, y_pred: Any) -> dict[str, Any]:
        metrics = regression_metrics(y_true, y_pred)
        return build_evaluation_report("sc", metrics, self.config)
