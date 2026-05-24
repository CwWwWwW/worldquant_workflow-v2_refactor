from __future__ import annotations

import math
from typing import Any


def _safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        out = float(value)
        if math.isnan(out) or math.isinf(out):
            return default
        return out
    except Exception:
        return default


def model_match_rate(matches: list[bool] | int, total: int | None = None) -> float | None:
    if isinstance(matches, int):
        count = matches
        denom = int(total or 0)
    else:
        count = sum(1 for item in matches if item)
        denom = len(matches)
    if denom <= 0:
        return None
    return float(count / denom)


def support_coverage(supported: list[bool] | int, total: int | None = None) -> float | None:
    if isinstance(supported, int):
        count = supported
        denom = int(total or 0)
    else:
        count = sum(1 for item in supported if item)
        denom = len(supported)
    if denom <= 0:
        return None
    return float(count / denom)


def estimated_reward_delta(values: list[Any]) -> float | None:
    parsed = [_safe_float(v) for v in values]
    valid = [v for v in parsed if v is not None]
    return None if not valid else float(sum(valid) / len(valid))


def estimated_risk_delta(values: list[Any]) -> float | None:
    return estimated_reward_delta(values)


def failure_delta(values: list[Any]) -> float | None:
    return estimated_reward_delta(values)


def replay_pass_gate(metrics: dict[str, Any], config: Any | None = None) -> dict[str, Any]:
    reasons: list[str] = []

    def require_metric(name: str) -> float | None:
        value = _safe_float(metrics.get(name))
        if value is None:
            reasons.append(f"{name}:insufficient_data")
        return value

    sample_count = int(_safe_float(metrics.get("sample_count"), 0) or 0)
    support = require_metric("support_coverage")
    reward = require_metric("estimated_reward_delta")
    risk = require_metric("estimated_sc_risk_delta")
    failure = require_metric("estimated_failure_delta")

    min_decisions = int(getattr(config, "offline_replay_min_decisions", 100) or 100)
    min_support = float(getattr(config, "promotion_min_support_coverage", 0.65) or 0.65)
    min_reward = float(getattr(config, "promotion_min_reward_improvement", 0.05) or 0.05)
    max_risk = float(getattr(config, "promotion_max_sc_risk_delta", 0.03) or 0.03)
    max_failure = float(getattr(config, "promotion_max_failure_rate_delta", 0.03) or 0.03)

    if sample_count < min_decisions:
        reasons.append("sample_count_below_minimum")
    if support is not None and support < min_support:
        reasons.append("support_coverage_below_minimum")
    if reward is not None and reward < min_reward:
        reasons.append("reward_improvement_below_minimum")
    if risk is not None and risk > max_risk:
        reasons.append("sc_risk_delta_above_maximum")
    if failure is not None and failure > max_failure:
        reasons.append("failure_delta_above_maximum")

    return {"replay_pass": not reasons, "reasons": reasons}
