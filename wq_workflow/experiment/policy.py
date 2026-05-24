from __future__ import annotations

from typing import Any


class ExperimentBudgetPolicy:
    """Conservative advisory policy for phase 4B budget planning."""

    def __init__(self, *, config: Any | None = None) -> None:
        self.config = config
        self.min_samples_for_adjustment = max(1, _int(config, "experiment_budget_min_samples_for_adjustment", 30))
        self.high_failure_rate_threshold = _ratio(config, "experiment_budget_high_failure_rate_threshold", 0.70)
        self.high_sc_abs_max_threshold = _ratio(config, "experiment_budget_high_sc_abs_max_threshold", 0.70)
        self.high_quality_pass_threshold = _ratio(config, "experiment_budget_high_quality_pass_threshold", 0.30)
        self.legacy_min_ratio = _ratio(config, "experiment_budget_legacy_min_ratio", 0.15)
        self.random_min_ratio = _ratio(config, "experiment_budget_random_min_ratio", 0.05)
        self.treatment_max_ratio = _ratio(config, "experiment_budget_treatment_max_ratio", 0.40)

    def score_arm(self, summary: Any) -> float:
        score = 1.0
        if self.is_insufficient_sample(summary):
            score *= 0.85
        if self.is_high_failure(summary):
            score *= 0.45
        if self.is_high_sc_risk(summary):
            score *= 0.50
        if _float(getattr(summary, "avg_reward", None), None) is not None and float(getattr(summary, "avg_reward") or 0.0) > 0:
            score *= 1.25
        if self.is_high_quality(summary):
            score *= 1.20
        if _int_value(getattr(summary, "success_count", 0), 0) > _int_value(getattr(summary, "failure_count", 0), 0):
            score *= 1.10
        return max(0.01, float(score))

    def reason_codes(self, summary: Any) -> list[str]:
        reasons: list[str] = []
        if self.is_insufficient_sample(summary):
            reasons.append("insufficient_samples")
        if self.is_high_failure(summary):
            reasons.append("high_failure_rate")
        if self.is_high_sc_risk(summary):
            reasons.append("high_sc_risk")
        reward = _float(getattr(summary, "avg_reward", None), None)
        if reward is not None and reward > 0:
            reasons.append("positive_reward")
        if self.is_high_quality(summary):
            reasons.append("high_quality_pass_rate")
        if _int_value(getattr(summary, "success_count", 0), 0) > _int_value(getattr(summary, "failure_count", 0), 0):
            reasons.append("success_count_signal")
        if not reasons:
            reasons.append("neutral_history")
        return reasons

    def clamp_ratio(self, ratio: float, min_ratio: float, max_ratio: float) -> float:
        return max(float(min_ratio), min(float(max_ratio), float(ratio)))

    def is_insufficient_sample(self, summary: Any) -> bool:
        return _int_value(getattr(summary, "sample_count", 0), 0) < self.min_samples_for_adjustment

    def is_high_failure(self, summary: Any) -> bool:
        sample_count = _int_value(getattr(summary, "sample_count", 0), 0)
        if sample_count <= 0:
            return False
        failure_count = _int_value(getattr(summary, "failure_count", 0), 0)
        return (failure_count / sample_count) >= self.high_failure_rate_threshold

    def is_high_sc_risk(self, summary: Any) -> bool:
        value = _float(getattr(summary, "avg_platform_sc_abs_max", None), None)
        return value is not None and value >= self.high_sc_abs_max_threshold

    def is_high_quality(self, summary: Any) -> bool:
        value = _float(getattr(summary, "quality_pass_rate", None), None)
        return value is not None and value >= self.high_quality_pass_threshold


def _int(config: Any | None, name: str, default: int) -> int:
    return _int_value(getattr(config, name, default), default)


def _ratio(config: Any | None, name: str, default: float) -> float:
    value = _float(getattr(config, name, default), default)
    return max(0.0, min(1.0, float(value)))


def _float(value: Any, default: Any = 0.0) -> Any:
    try:
        if value is None or value == "":
            return default
        number = float(value)
        return number if number == number and number not in {float("inf"), float("-inf")} else default
    except (TypeError, ValueError):
        return default


def _int_value(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
