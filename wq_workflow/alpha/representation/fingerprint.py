from __future__ import annotations

from typing import Any

from .ast import AlphaASTNode
from .normalizer import stable_hash


def _short_hash(text: str) -> str:
    return stable_hash(text)[:16]


def numeric_bucket(value: Any) -> str:
    try:
        number = abs(float(value))
    except Exception:
        return "unknown"
    if number == 0:
        return "0"
    if number == 1:
        return "1"
    if number <= 5:
        return "2-5"
    if number <= 10:
        return "6-10"
    if number <= 20:
        return "11-20"
    if number <= 60:
        return "21-60"
    if number <= 120:
        return "61-120"
    return ">120"


def expression_fingerprint(representation: Any) -> str:
    return _short_hash(str(getattr(representation, "normalized_expression", "") or ""))


def operator_fingerprint(operator_sequence: list[str]) -> str:
    return _short_hash("op|" + "|".join(operator_sequence or []))


def field_fingerprint(field_sequence: list[str]) -> str:
    return _short_hash("field|" + "|".join(field_sequence or []))


def parameter_fingerprint(numeric_params: list[float]) -> str:
    return _short_hash("param|" + "|".join(numeric_bucket(v) for v in (numeric_params or [])))


def _subtree_hash(node: AlphaASTNode | None) -> str:
    if node is None:
        return _short_hash("empty")
    if node.node_type == "operator":
        child_hashes = ",".join(_subtree_hash(child) for child in node.children)
        return _short_hash(f"operator({node.value}:{child_hashes})")
    if node.node_type == "field":
        return _short_hash(f"field({node.value})")
    if node.node_type == "number":
        return _short_hash(f"number({numeric_bucket(node.value)})")
    return _short_hash(f"unknown({node.value})")


def subtree_fingerprints(ast: AlphaASTNode | None) -> list[str]:
    if ast is None:
        return []
    return [_subtree_hash(node) for node in ast.walk()]


def infer_behavior_family(root_operator: str = "", operator_sequence: list[str] | None = None) -> str:
    operators = operator_sequence or []
    root = root_operator or (operators[0] if operators else "")
    if not root:
        return "raw"
    if root == "trade_when" or "trade_when" in operators:
        return "trade_control"
    if root.startswith("group_") or any(op.startswith("group_") for op in operators):
        return "group"
    if root.startswith("ts_") or any(op.startswith("ts_") for op in operators):
        return "time_series"
    if "rank" in operators or root == "rank":
        return "rank"
    if root.startswith("vec_") or any(op.startswith("vec_") for op in operators):
        return "vector"
    return root


def behavior_fingerprint(representation: Any) -> str:
    path = getattr(representation, "operator_path_features", {}) or {}
    numeric_params = getattr(representation, "numeric_params", []) or []
    parts = [
        str(getattr(representation, "root_operator", "") or ""),
        "|".join(getattr(representation, "operator_sequence", []) or []),
        str(path.get("ts_operator_count", 0)),
        str(path.get("group_operator_count", 0)),
        str(path.get("rank_operator_count", 0)),
        str(getattr(representation, "field_count", 0) or 0),
        "|".join(numeric_bucket(v) for v in numeric_params),
        str(getattr(representation, "behavior_family", "") or ""),
    ]
    return _short_hash("behavior|" + "|".join(parts))
