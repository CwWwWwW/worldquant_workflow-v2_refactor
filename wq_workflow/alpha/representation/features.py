from __future__ import annotations

from typing import Any

from .fingerprint import (
    behavior_fingerprint as build_behavior_fingerprint,
    field_fingerprint,
    infer_behavior_family,
    operator_fingerprint,
    parameter_fingerprint,
    subtree_fingerprints,
)
from .normalizer import normalize_expression, stable_hash
from .operator_path import operator_path_features
from .parser import parse_expression
from .schema import AlphaRepresentation
from .tokenizer import tokenize


def expression_hash(expression: str) -> str:
    return stable_hash(expression or "")[:16]


def hash_to_unit_float(text: str) -> float:
    if not text:
        return 0.0
    h = stable_hash(text)
    return int(h[:8], 16) / 0xFFFFFFFF


def _safe_float_list(values: list[Any]) -> list[float]:
    out: list[float] = []
    for value in values or []:
        try:
            out.append(float(value))
        except Exception:
            pass
    return out


def _numeric_stats(numbers: list[float]) -> tuple[float, float, float]:
    if not numbers:
        return 0.0, 0.0, 0.0
    return sum(numbers) / len(numbers), max(numbers), min(numbers)


def _feature_vector(features: dict[str, Any]) -> list[float]:
    vector: list[float] = []
    for key in sorted(features):
        value = features.get(key)
        if isinstance(value, bool):
            vector.append(1.0 if value else 0.0)
        elif isinstance(value, (int, float)):
            try:
                vector.append(float(value))
            except Exception:
                pass
    return vector


def _minimal_representation(raw: str, normalized: str, *, parse_status: str = "failed", parse_error: str = "") -> AlphaRepresentation:
    features = {
        "expression_length": len(raw or ""),
        "normalized_length": len(normalized or ""),
        "ast_depth": 0,
        "node_count": 0,
        "operator_count": 0,
        "field_count": 0,
        "unique_operator_count": 0,
        "unique_field_count": 0,
        "numeric_param_count": 0,
        "numeric_param_mean": 0.0,
        "numeric_param_max": 0.0,
        "numeric_param_min": 0.0,
        "has_ts_operator": False,
        "has_rank_operator": False,
        "has_group_operator": False,
        "has_neutralize_operator": False,
        "has_trade_when": False,
        "has_decay": False,
        "has_vector_operator": False,
        "has_arithmetic_operator": False,
        "root_operator_hash": 0.0,
        "operator_path_hash": 0.0,
        "field_fingerprint_hash": 0.0,
        "behavior_fingerprint_hash": 0.0,
        "subtree_count": 0,
    }
    rep = AlphaRepresentation(
        raw_expression=raw or "",
        normalized_expression=normalized or "",
        expression_hash=expression_hash(normalized or ""),
        parse_status=parse_status,
        parse_error=parse_error,
        behavior_family="raw",
        behavior_fingerprint=expression_hash("behavior|raw"),
        features=features,
    )
    rep.feature_vector = _feature_vector(features)
    return rep


def build_alpha_representation(expression: str) -> AlphaRepresentation:
    raw = str(expression or "")
    normalized = normalize_expression(raw)
    try:
        tokenize(raw)  # Tokenization is intentionally fail-soft; parser tokenizes again.
        ast = parse_expression(raw) if raw else None
        if ast is None:
            return _minimal_representation(raw, normalized, parse_status="ok")

        operators = [str(op) for op in ast.operators()]
        fields = [str(field) for field in ast.fields()]
        numbers = _safe_float_list(ast.numbers())
        path_features = operator_path_features(ast)
        root_operator = str(path_features.get("root_operator") or (operators[0] if operators else ""))
        subtrees = subtree_fingerprints(ast)
        op_fp = operator_fingerprint(operators)
        field_fp = field_fingerprint(fields)
        param_fp = parameter_fingerprint(numbers)
        behavior_family = infer_behavior_family(root_operator, operators)

        rep = AlphaRepresentation(
            raw_expression=raw,
            normalized_expression=normalized,
            expression_hash=expression_hash(normalized),
            parse_status="ok",
            ast=ast,
            operator_sequence=operators,
            field_sequence=fields,
            numeric_params=numbers,
            root_operator=root_operator,
            ast_depth=ast.max_depth(),
            node_count=ast.node_count(),
            operator_count=len(operators),
            field_count=len(fields),
            unique_operator_count=len(set(operators)),
            unique_field_count=len(set(fields)),
            subtree_fingerprints=subtrees,
            operator_path_features=path_features,
            behavior_family=behavior_family,
        )
        rep.behavior_fingerprint = build_behavior_fingerprint(rep)
        numeric_mean, numeric_max, numeric_min = _numeric_stats(numbers)
        operator_path_hash_source = "|".join(path_features.get("operator_bigrams") or operators)
        features: dict[str, Any] = {
            "expression_length": len(raw),
            "normalized_length": len(normalized),
            "ast_depth": rep.ast_depth,
            "node_count": rep.node_count,
            "operator_count": rep.operator_count,
            "field_count": rep.field_count,
            "unique_operator_count": rep.unique_operator_count,
            "unique_field_count": rep.unique_field_count,
            "numeric_param_count": len(numbers),
            "numeric_param_mean": numeric_mean,
            "numeric_param_max": numeric_max,
            "numeric_param_min": numeric_min,
            "has_ts_operator": bool(path_features.get("ts_operator_count")),
            "has_rank_operator": bool(path_features.get("rank_operator_count")),
            "has_group_operator": bool(path_features.get("group_operator_count")),
            "has_neutralize_operator": any("neutralize" in op for op in operators),
            "has_trade_when": "trade_when" in operators,
            "has_decay": any("decay" in op for op in operators),
            "has_vector_operator": bool(path_features.get("vector_operator_count")),
            "has_arithmetic_operator": bool(path_features.get("arithmetic_operator_count")),
            "root_operator_hash": hash_to_unit_float(root_operator),
            "operator_path_hash": hash_to_unit_float(operator_path_hash_source),
            "field_fingerprint_hash": hash_to_unit_float(field_fp),
            "behavior_fingerprint_hash": hash_to_unit_float(rep.behavior_fingerprint),
            "subtree_count": len(subtrees),
            "operator_fingerprint_hash": hash_to_unit_float(op_fp),
            "parameter_fingerprint_hash": hash_to_unit_float(param_fp),
        }
        rep.features = features
        rep.feature_vector = _feature_vector(features)
        return rep
    except Exception as exc:
        return _minimal_representation(raw, normalized, parse_status="failed", parse_error=str(exc))
