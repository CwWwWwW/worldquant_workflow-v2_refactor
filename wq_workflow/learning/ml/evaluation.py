from __future__ import annotations

import math
from typing import Any

from .availability import require_numpy, require_sklearn_metrics


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
        if math.isnan(out) or math.isinf(out):
            return default
        return out
    except Exception:
        return default


def regression_metrics(y_true: Any, y_pred: Any) -> dict[str, Any]:
    np = require_numpy()
    yt = list(y_true or []) if np is None else np.asarray(y_true, dtype=float)
    yp = list(y_pred or []) if np is None else np.asarray(y_pred, dtype=float)
    try:
        count = int(len(yt))
    except Exception:
        count = 0
    if count == 0:
        return {"mae": None, "rmse": None, "sample_count": 0, "validation_size": 0, "y_mean": None, "pred_mean": None}
    if np is not None:
        err = np.nan_to_num(yt - yp, nan=0.0, posinf=0.0, neginf=0.0)
        return {
            "mae": float(np.mean(np.abs(err))),
            "rmse": float(np.sqrt(np.mean(err * err))),
            "sample_count": count,
            "validation_size": count,
            "y_mean": float(np.mean(yt)),
            "pred_mean": float(np.mean(yp)),
        }
    errors = [_safe_float(a) - _safe_float(b) for a, b in zip(yt, yp)]
    return {
        "mae": sum(abs(e) for e in errors) / max(1, len(errors)),
        "rmse": math.sqrt(sum(e * e for e in errors) / max(1, len(errors))),
        "sample_count": count,
        "validation_size": count,
        "y_mean": sum(_safe_float(v) for v in yt) / max(1, count),
        "pred_mean": sum(_safe_float(v) for v in yp) / max(1, count),
    }


def evaluate_regression(y_true: Any, y_pred: Any) -> dict[str, Any]:
    np = require_numpy()
    metrics_mod = require_sklearn_metrics()
    if np is None or metrics_mod is None:
        return {"available": False, "reason": "numpy_or_sklearn_unavailable"}
    try:
        yt = np.nan_to_num(np.asarray(y_true, dtype=float), nan=0.0, posinf=0.0, neginf=0.0)
        yp = np.nan_to_num(np.asarray(y_pred, dtype=float), nan=0.0, posinf=0.0, neginf=0.0)
        mae = float(metrics_mod["mean_absolute_error"](yt, yp))
        mse = float(metrics_mod["mean_squared_error"](yt, yp))
        return {"available": True, "mae": mae, "mse": mse, "rmse": float(np.sqrt(mse)), "sample_count": int(len(yt))}
    except Exception as exc:
        return {"available": False, "reason": "evaluation_error", "error": str(exc)}


def classification_metrics(y_true: Any, y_pred: Any) -> dict[str, Any]:
    try:
        true_values = list(y_true) if y_true is not None else []
    except Exception:
        true_values = []
    try:
        pred_values = list(y_pred) if y_pred is not None else []
    except Exception:
        pred_values = []
    yt = [1 if _safe_float(v) >= 0.5 else 0 for v in true_values]
    yp = [1 if _safe_float(v) >= 0.5 else 0 for v in pred_values]
    count = min(len(yt), len(yp))
    if count == 0:
        return {"precision": None, "recall": None, "accuracy": None, "positive_rate": None, "success_recall": None, "sample_count": 0, "validation_size": 0}
    yt = yt[:count]
    yp = yp[:count]
    tp = sum(1 for a, b in zip(yt, yp) if a == 1 and b == 1)
    fp = sum(1 for a, b in zip(yt, yp) if a == 0 and b == 1)
    fn = sum(1 for a, b in zip(yt, yp) if a == 1 and b == 0)
    correct = sum(1 for a, b in zip(yt, yp) if a == b)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    return {
        "precision": float(precision),
        "recall": float(recall),
        "success_recall": float(recall),
        "accuracy": float(correct / count),
        "positive_rate": float(sum(yt) / count),
        "sample_count": count,
        "validation_size": count,
    }


def evaluate_binary_classification(y_true: Any, y_pred_label: Any, y_pred_score: Any | None = None) -> dict[str, Any]:
    metrics_mod = require_sklearn_metrics()
    if metrics_mod is None:
        return {"available": False, "reason": "sklearn_unavailable"}
    try:
        precision = float(metrics_mod["precision_score"](y_true, y_pred_label, zero_division=0))
        recall = float(metrics_mod["recall_score"](y_true, y_pred_label, zero_division=0))
        result = {"available": True, "precision": precision, "recall": recall, "sample_count": int(len(y_true))}
        if y_pred_score is not None:
            result["has_score"] = True
        return result
    except Exception as exc:
        return {"available": False, "reason": "evaluation_error", "error": str(exc)}


def coverage_metrics(items: Any, *, key: str | None = None) -> dict[str, Any]:
    values: list[Any] = []
    for item in items or []:
        if key and isinstance(item, dict):
            values.append(item.get(key))
        else:
            values.append(item)
    total = len(values)
    unique = len({str(v) for v in values if v is not None and str(v) != ""})
    return {"coverage": float(unique / total) if total else 0.0, "unique_count": unique, "sample_count": total}


def ranking_metrics(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return {"status": "not_implemented", "sample_count": 0}


def _metric(metrics: dict[str, Any], *names: str, default: float | None = None) -> float | None:
    for name in names:
        if name in metrics and metrics.get(name) is not None:
            return _safe_float(metrics.get(name))
    return default


def validation_gate(task_name: str, metrics: dict[str, Any] | None, config: Any | None = None) -> dict[str, Any]:
    m = metrics or {}
    task = str(task_name or "").lower()
    sample_count = int(_metric(m, "sample_count", "train_sample_count", default=0) or 0)
    reasons: list[str] = []
    passed = True

    def require(cond: bool, reason: str) -> None:
        nonlocal passed
        if not cond:
            passed = False
            reasons.append(reason)

    if task == "sc":
        min_samples = int(getattr(config, "sc_learning_min_samples", getattr(config, "ml_min_samples", 200)) or 200)
        max_mae = float(getattr(config, "sc_model_max_mae", 0.15) or 0.15)
        require(sample_count >= min_samples, "not_enough_samples")
        require((_metric(m, "mae", default=999.0) or 999.0) <= max_mae, "mae_above_threshold")
    elif task == "parent":
        min_samples = int(getattr(config, "parent_learning_min_samples", 200) or 200)
        max_mae = float(getattr(config, "parent_model_max_mae", 0.20) or 0.20)
        min_recall = float(getattr(config, "parent_model_min_success_recall", 0.60) or 0.60)
        require(sample_count >= min_samples, "not_enough_samples")
        mae_ok = (_metric(m, "mae", "reward_mae", default=999.0) or 999.0) <= max_mae
        recall_ok = (_metric(m, "success_recall", "recall", default=-1.0) or -1.0) >= min_recall
        require(mae_ok or recall_ok, "quality_below_threshold")
    elif task == "policy":
        min_samples = int(getattr(config, "policy_learning_min_samples", 200) or 200)
        max_mae = float(getattr(config, "policy_model_max_mae", 0.25) or 0.25)
        min_cov = float(getattr(config, "policy_min_action_coverage", 0.30) or 0.30)
        require(sample_count >= min_samples, "not_enough_samples")
        require((_metric(m, "action_coverage", "coverage", default=0.0) or 0.0) >= min_cov, "action_coverage_below_threshold")
        require((_metric(m, "mae", "reward_mae", default=999.0) or 999.0) <= max_mae, "mae_above_threshold")
    elif task in {"simulator", "outcome"}:
        min_samples = int(getattr(config, "simulator_learning_min_samples", 200) or 200)
        min_recall = float(getattr(config, "simulator_model_min_success_recall", 0.70) or 0.70)
        require(sample_count >= min_samples, "not_enough_samples")
        require((_metric(m, "success_recall", "recall", default=-1.0) or -1.0) >= min_recall, "success_recall_below_threshold")
    else:
        require(sample_count > 0, "not_enough_samples")
    return {"passed": bool(passed), "reasons": reasons, "task_name": task_name, "metrics": m}


def passes_activation_gate(metrics: dict[str, Any], config: Any | None, task_name: str) -> bool:
    if not (metrics or {}).get("available", True):
        return False
    sample_count = int((metrics or {}).get("sample_count", (metrics or {}).get("train_sample_count", 0)) or 0)
    min_samples = getattr(config, f"{task_name}_min_samples", None)
    if min_samples is None:
        min_samples = getattr(config, "ml_min_samples", 200)
    if sample_count < int(min_samples or 200):
        return False
    max_mae = getattr(config, f"{task_name}_max_mae", None)
    if max_mae is not None and (metrics or {}).get("mae") is not None:
        if float((metrics or {})["mae"]) > float(max_mae):
            return False
    if getattr(config, "ml_require_validation_pass", True):
        gate = validation_gate(task_name, metrics or {}, config)
        return bool(gate.get("passed"))
    return True


def build_evaluation_report(task_name: str, metrics: dict[str, Any] | None, config: Any | None = None, **extra: Any) -> dict[str, Any]:
    gate = validation_gate(task_name, metrics or {}, config)
    return {"task_name": task_name, "metrics": metrics or {}, "validation_gate": gate, **extra}
