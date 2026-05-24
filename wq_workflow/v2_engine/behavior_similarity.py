from __future__ import annotations

from typing import Any

from .behavior_fingerprint import build_behavior_fingerprint


CATEGORICAL_FIELDS = ["family", "delay_family", "decay_family", "turnover_class", "neutralization_type"]
NUMERIC_FIELDS = [
    "group_ops",
    "bucket_ops",
    "momentum_bias",
    "mean_reversion_bias",
    "volatility_bias",
    "active_frequency",
]
BOOLEAN_FIELDS = ["trade_when", "event_driven"]


def compute_behavior_similarity(left: dict[str, Any] | str, right: dict[str, Any] | str) -> float:
    left_fp = _fingerprint(left)
    right_fp = _fingerprint(right)
    categorical = _avg([1.0 if str(left_fp.get(key)) == str(right_fp.get(key)) else 0.0 for key in CATEGORICAL_FIELDS], 0.0)
    numeric = _avg([_numeric_similarity(left_fp.get(key), right_fp.get(key)) for key in NUMERIC_FIELDS], 0.0)
    boolean = _avg([1.0 if bool(left_fp.get(key)) == bool(right_fp.get(key)) else 0.0 for key in BOOLEAN_FIELDS], 0.0)
    weighted = categorical * 0.42 + numeric * 0.40 + boolean * 0.18
    return round(max(0.0, min(1.0, weighted)), 6)


def compute_final_similarity(structure_similarity: float, semantic_similarity: float, behavior_similarity: float) -> float:
    weighted = structure_similarity * 0.25 + semantic_similarity * 0.25 + behavior_similarity * 0.50
    return round(max(0.0, min(1.0, weighted)), 6)


def _fingerprint(value: dict[str, Any] | str) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return build_behavior_fingerprint(str(value or ""))


def _numeric_similarity(left: Any, right: Any) -> float:
    left_number = _number(left)
    right_number = _number(right)
    if left_number == 0.0 and right_number == 0.0:
        return 1.0
    return 1.0 - min(1.0, abs(left_number - right_number) / max(abs(left_number), abs(right_number), 1.0))


def _number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _avg(values: list[float], default: float) -> float:
    return sum(values) / len(values) if values else default
