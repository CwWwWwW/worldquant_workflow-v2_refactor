from __future__ import annotations

OPERATOR_ARITY = {
    "abs": (1, 1),
    "bucket": (2, 2),
    "densify": (1, 1),
    "group_mean": (3, 3),
    "group_neutralize": (2, 2),
    "group_rank": (2, 2),
    "group_zscore": (2, 2),
    "hump": (1, 2),
    "inverse": (1, 1),
    "log": (1, 1),
    "rank": (1, 1),
    "scale": (1, 1),
    "signed_power": (2, 2),
    "sign": (1, 1),
    "trade_when": (3, 3),
    "ts_backfill": (2, 2),
    "ts_corr": (3, 3),
    "ts_count_nans": (2, 2),
    "ts_decay_exp_window": (2, 3),
    "ts_delta": (2, 2),
    "ts_mean": (2, 2),
    "ts_product": (2, 2),
    "ts_rank": (2, 2),
    "ts_scale": (2, 2),
    "ts_std_dev": (2, 2),
    "ts_sum": (2, 2),
    "ts_zscore": (2, 2),
    "vec_avg": (1, 1),
    "vec_count": (1, 1),
    "winsorize": (1, 2),
}

SAFE_FIELDS = {
    "cap",
    "close",
    "high",
    "industry",
    "low",
    "market",
    "open",
    "returns",
    "sector",
    "subindustry",
    "volume",
    "vwap",
    "adv20",
    "exchange",
}

PRICE_FIELDS = {"close", "open", "high", "low", "vwap"}
VOLUME_FIELDS = {"volume", "adv20"}
RETURN_FIELDS = {"returns"}
FUNDAMENTAL_FIELDS = {"cap"}
GROUP_FIELDS = {"industry", "sector", "subindustry", "market", "exchange"}

FIELD_CATEGORIES = {
    **{field: "price" for field in PRICE_FIELDS},
    **{field: "volume" for field in VOLUME_FIELDS},
    **{field: "return" for field in RETURN_FIELDS},
    **{field: "fundamental" for field in FUNDAMENTAL_FIELDS},
    **{field: "group" for field in GROUP_FIELDS},
}

TS_OPERATORS = {name for name in OPERATOR_ARITY if name.startswith("ts_")}
GROUP_OPERATORS = {"group_mean", "group_neutralize", "group_rank", "group_zscore", "bucket"}
NEUTRALIZATION_OPERATORS = {"group_neutralize", "group_zscore", "group_rank"}

OPERATOR_EMBEDDINGS = {
    "rank": {"ranking", "cross_sectional", "relative"},
    "ts_rank": {"ranking", "time_series", "relative"},
    "ts_mean": {"trend", "smooth", "time_series"},
    "ts_decay_exp_window": {"memory", "smooth", "time_series"},
    "hump": {"turnover_reduction", "smooth"},
    "ts_delta": {"momentum", "change", "time_series"},
    "ts_corr": {"relationship", "time_series"},
    "ts_zscore": {"standardize", "time_series"},
    "ts_scale": {"scale", "time_series"},
    "winsorize": {"robust", "outlier_control"},
    "scale": {"normalize", "risk_control"},
    "group_neutralize": {"neutralize", "group", "risk_control"},
    "group_zscore": {"standardize", "group", "risk_control"},
    "bucket": {"bucket", "grouping"},
    "inverse": {"transform", "nonlinear"},
    "signed_power": {"transform", "nonlinear"},
    "trade_when": {"event", "regime", "gating"},
}

ILLEGAL_NESTING = {
    ("rank", "rank"): "redundant rank nesting",
    ("group_neutralize", "group_neutralize"): "over-neutralized",
    ("group_zscore", "group_zscore"): "over-standardized",
}

BAD_COMBINATIONS = {
    "rank(rank())": "unstable",
    "group_neutralize(group_neutralize())": "over-neutralized",
}


def field_category(field: str) -> str:
    return FIELD_CATEGORIES.get((field or "").lower(), "unknown")


def semantic_safe_field_swap(left: str, right: str) -> bool:
    return field_category(left) != "unknown" and field_category(left) == field_category(right)
