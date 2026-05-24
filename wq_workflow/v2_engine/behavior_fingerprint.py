from __future__ import annotations

from typing import Any

from ..core.ast import ASTNode, walk
from ..core.parser import ExpressionParser, ParseError
from ..safe_io import finite_float


FAMILY_NAMES = {
    "momentum",
    "mean_reversion",
    "volatility",
    "event",
    "regression",
    "sentiment",
    "group",
    "hybrid",
    "legacy",
}

GROUP_FIELDS = {"sector", "industry", "subindustry", "exchange", "market"}
VOLATILITY_OPERATORS = {"ts_std_dev", "ts_zscore", "ts_scale"}
MOMENTUM_OPERATORS = {"ts_delta", "ts_rank", "ts_sum", "ts_corr"}
MEAN_REVERSION_OPERATORS = {"ts_mean", "ts_zscore", "ts_decay_exp_window", "hump"}
REGRESSION_TOKENS = {"regression", "regression_neut", "regression_neutralize"}
SENTIMENT_TOKENS = {"sentiment", "news", "nws", "analyst", "fear"}


def build_behavior_fingerprint(alpha_expression: str) -> dict[str, Any]:
    """Build a deterministic, AST-only behavior fingerprint.

    Unparseable legacy expressions intentionally fall back to the legacy family
    instead of trying to infer behavior from brittle text fragments.
    """

    try:
        ast = ExpressionParser().parse(alpha_expression)
    except (ParseError, RecursionError, ValueError):
        return _legacy_fingerprint()

    operators = [node.name.lower() for node in walk(ast) if node.type == "operator"]
    fields = [node.name.lower() for node in walk(ast) if node.type == "field"]
    variables = [node.name.lower() for node in walk(ast) if node.type == "variable"]
    comparisons = [node for node in walk(ast) if node.type == "comparison"]
    windows = _windows(ast)

    trade_when = "trade_when" in operators
    group_ops = sum(1 for name in operators if name.startswith("group_"))
    bucket_ops = operators.count("bucket")
    event_driven = bool(trade_when or comparisons)
    neutralization_type = _neutralization_type(operators, fields)
    delay_family = _delay_family(operators)
    decay_family = _decay_family(operators, windows)
    momentum_bias = _momentum_bias(operators, fields, variables)
    mean_reversion_bias = _mean_reversion_bias(operators, fields, variables)
    volatility_bias = _volatility_bias(operators, fields, variables)
    active_frequency = _active_frequency(trade_when, comparisons, windows, operators)
    turnover_class = _turnover_class(active_frequency, operators, windows)
    family = _infer_family(
        operators=operators,
        fields=fields,
        variables=variables,
        trade_when=trade_when,
        group_ops=group_ops,
        bucket_ops=bucket_ops,
        momentum_bias=momentum_bias,
        mean_reversion_bias=mean_reversion_bias,
        volatility_bias=volatility_bias,
    )

    return {
        "family": family,
        "trade_when": trade_when,
        "group_ops": group_ops,
        "bucket_ops": bucket_ops,
        "delay_family": delay_family,
        "decay_family": decay_family,
        "turnover_class": turnover_class,
        "event_driven": event_driven,
        "momentum_bias": round(momentum_bias, 6),
        "mean_reversion_bias": round(mean_reversion_bias, 6),
        "volatility_bias": round(volatility_bias, 6),
        "neutralization_type": neutralization_type,
        "active_frequency": round(active_frequency, 6),
    }


def _legacy_fingerprint() -> dict[str, Any]:
    return {
        "family": "legacy",
        "trade_when": False,
        "group_ops": 0,
        "bucket_ops": 0,
        "delay_family": "unknown",
        "decay_family": "unknown",
        "turnover_class": "unknown",
        "event_driven": False,
        "momentum_bias": 0.0,
        "mean_reversion_bias": 0.0,
        "volatility_bias": 0.0,
        "neutralization_type": "unknown",
        "active_frequency": 1.0,
    }


def _windows(ast: ASTNode) -> list[int]:
    values: list[int] = []
    for node in walk(ast):
        if node.type != "operator":
            continue
        value = node.parameters.get("window")
        if isinstance(value, int):
            values.append(value)
        for child in node.children:
            if child.type == "number":
                number = finite_float(child.value)
                if number.is_integer() and number >= 2:
                    values.append(int(number))
    return values


def _neutralization_type(operators: list[str], fields: list[str]) -> str:
    if "group_neutralize" in operators:
        return "group_neutralize"
    if "group_zscore" in operators:
        return "group_zscore"
    if "group_rank" in operators:
        return "group_rank"
    if "bucket" in operators:
        return "bucket"
    if any(field in GROUP_FIELDS for field in fields):
        return "group_field"
    return "none"


def _delay_family(operators: list[str]) -> str:
    if "delay" in operators or "ts_delay" in operators:
        return "explicit_delay"
    if "ts_delta" in operators:
        return "delta"
    if "ts_backfill" in operators:
        return "backfill"
    return "none"


def _decay_family(operators: list[str], windows: list[int]) -> str:
    if "ts_decay_exp_window" in operators:
        return "exp_decay"
    if "hump" in operators:
        return "hump"
    if "ts_mean" in operators and max(windows or [0]) >= 20:
        return "long_smoothing"
    if "ts_mean" in operators:
        return "short_smoothing"
    return "none"


def _momentum_bias(operators: list[str], fields: list[str], variables: list[str]) -> float:
    score = 0.0
    score += 0.24 * sum(1 for name in operators if name in MOMENTUM_OPERATORS)
    score += 0.18 if "returns" in fields else 0.0
    score += 0.15 if "ts_delta" in operators else 0.0
    score += 0.12 if any("momentum" in item or "trend" in item for item in variables) else 0.0
    return min(score, 1.0)


def _mean_reversion_bias(operators: list[str], fields: list[str], variables: list[str]) -> float:
    score = 0.0
    score += 0.18 * sum(1 for name in operators if name in MEAN_REVERSION_OPERATORS)
    score += 0.18 if "ts_zscore" in operators else 0.0
    score += 0.12 if "rank" in operators and ("returns" in fields or "close" in fields) else 0.0
    score += 0.12 if any("revert" in item or "mean" in item for item in variables) else 0.0
    return min(score, 1.0)


def _volatility_bias(operators: list[str], fields: list[str], variables: list[str]) -> float:
    score = 0.0
    score += 0.28 * sum(1 for name in operators if name in VOLATILITY_OPERATORS)
    score += 0.18 if "abs" in operators and "returns" in fields else 0.0
    score += 0.16 if any("vol" in item or "std" in item for item in variables + fields) else 0.0
    return min(score, 1.0)


def _active_frequency(
    trade_when: bool,
    comparisons: list[ASTNode],
    windows: list[int],
    operators: list[str],
) -> float:
    frequency = 1.0
    if trade_when:
        frequency -= 0.28
    frequency -= min(0.20, len(comparisons) * 0.06)
    if max(windows or [0]) >= 126:
        frequency -= 0.16
    elif max(windows or [0]) >= 20:
        frequency -= 0.08
    if "hump" in operators or "ts_decay_exp_window" in operators:
        frequency -= 0.12
    return max(0.05, min(1.0, frequency))


def _turnover_class(active_frequency: float, operators: list[str], windows: list[int]) -> str:
    if "hump" in operators or active_frequency <= 0.55 or max(windows or [0]) >= 126:
        return "low"
    if active_frequency <= 0.80 or max(windows or [0]) >= 20:
        return "medium"
    return "high"


def _infer_family(
    *,
    operators: list[str],
    fields: list[str],
    variables: list[str],
    trade_when: bool,
    group_ops: int,
    bucket_ops: int,
    momentum_bias: float,
    mean_reversion_bias: float,
    volatility_bias: float,
) -> str:
    labels: list[tuple[str, float]] = []
    labels.append(("momentum", momentum_bias))
    labels.append(("mean_reversion", mean_reversion_bias))
    labels.append(("volatility", volatility_bias))
    labels.append(("event", 0.85 if trade_when else 0.0))
    labels.append(("group", min(1.0, group_ops * 0.35 + bucket_ops * 0.25)))
    labels.append(("regression", 0.9 if any(item in operators or item in variables for item in REGRESSION_TOKENS) else 0.0))
    labels.append(("sentiment", 0.8 if any(token in " ".join(fields + variables) for token in SENTIMENT_TOKENS) else 0.0))
    active = [name for name, score in labels if score >= 0.45]
    if len(active) >= 2 and max(score for _name, score in labels) < 0.90:
        return "hybrid"
    best = max(labels, key=lambda item: item[1])
    return best[0] if best[1] >= 0.30 else "hybrid"
