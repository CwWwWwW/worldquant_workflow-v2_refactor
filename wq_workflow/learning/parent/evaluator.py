from __future__ import annotations

from typing import Any

from wq_workflow.learning.ml.evaluation import build_evaluation_report, classification_metrics, regression_metrics


class ParentEvaluator:
    def __init__(self, *, config: Any | None = None) -> None:
        self.config = config

    def evaluate(self, reward_true: Any = None, reward_pred: Any = None, success_true: Any = None, success_pred: Any = None) -> dict[str, Any]:
        metrics: dict[str, Any] = {}
        if reward_true is not None and reward_pred is not None:
            rm = regression_metrics(reward_true, reward_pred)
            metrics.update(rm)
            metrics["reward_mae"] = rm.get("mae")
        if success_true is not None and success_pred is not None:
            cm = classification_metrics(success_true, success_pred)
            metrics.update({"success_" + k if k not in {"sample_count", "validation_size"} else k: v for k, v in cm.items()})
            metrics["success_recall"] = cm.get("recall")
        return build_evaluation_report("parent", metrics, self.config)
