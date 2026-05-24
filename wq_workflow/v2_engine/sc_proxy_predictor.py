from __future__ import annotations

import difflib
import json
import re
from collections import Counter
from typing import Any

from ..core.parser import ExpressionParser, ParseError
from ..core.semantic_similarity import SemanticSimilarity, operator_sequence
from ..safe_io import finite_float
from .behavior_fingerprint import build_behavior_fingerprint
from .behavior_similarity import compute_behavior_similarity, compute_final_similarity


def estimate_self_corr(
    expression: str,
    comparison_rows: list[dict[str, Any]] | None,
    metrics: dict[str, float] | None = None,
) -> dict[str, Any]:
    current_fp = build_behavior_fingerprint(expression)
    current_structure = _structure(expression)
    current_ast = _parse(expression)
    semantic = SemanticSimilarity()
    best = {
        "estimated_self_corr": 0.0,
        "nearest_alpha_id": "",
        "nearest_expression": "",
        "max_behavior_similarity": 0.0,
        "max_structure_similarity": 0.0,
        "max_semantic_similarity": 0.0,
        "max_final_similarity": 0.0,
    }

    for row in comparison_rows or []:
        other_expression = str(row.get("expression") or row.get("code") or "")
        if not other_expression:
            continue
        other_fp = _row_fingerprint(row, other_expression)
        behavior_score = compute_behavior_similarity(current_fp, other_fp)
        structure_score = _structure_similarity(current_structure, _row_structure(row, other_expression))
        semantic_score = _semantic_similarity(current_ast, _parse(other_expression), semantic)
        final_score = compute_final_similarity(structure_score, semantic_score, behavior_score)
        if final_score > best["max_final_similarity"]:
            best = {
                "estimated_self_corr": final_score,
                "nearest_alpha_id": str(row.get("alpha_id") or row.get("alpha_name") or ""),
                "nearest_expression": other_expression,
                "max_behavior_similarity": behavior_score,
                "max_structure_similarity": structure_score,
                "max_semantic_similarity": semantic_score,
                "max_final_similarity": final_score,
            }

    fitness = finite_float((metrics or {}).get("fitness"))
    similarity_limit = 0.85 if fitness > 1.0 else 0.75
    return {
        **best,
        "similarity_limit": similarity_limit,
        "behavior_fingerprint": current_fp,
        "behavior_family": str(current_fp.get("family") or "legacy"),
        "risk": "high" if best["estimated_self_corr"] > similarity_limit else "normal",
    }


def _row_fingerprint(row: dict[str, Any], expression: str) -> dict[str, Any]:
    value = row.get("behavior_fingerprint")
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            return parsed
    return build_behavior_fingerprint(expression)


def _row_structure(row: dict[str, Any], expression: str) -> dict[str, Any]:
    value = row.get("structure") or row.get("core_structure")
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            return parsed
    return _structure(expression)


def _parse(expression: str):
    try:
        return ExpressionParser().parse(expression)
    except (ParseError, RecursionError, ValueError):
        return None


def _semantic_similarity(left: Any, right: Any, semantic: SemanticSimilarity) -> float:
    if left is None or right is None:
        return 0.0
    return semantic.similarity(left, right)


def _structure(expression: str) -> dict[str, Any]:
    ast = _parse(expression)
    if ast is not None:
        return {
            "functions": operator_sequence(ast),
            "windows": [str(item) for item in re.findall(r"\b(?:ts_[A-Za-z_]+|delay|delta)\s*\([^)]*,\s*(\d+)", expression)],
            "groups": sorted(set(re.findall(r"\b(industry|sector|subindustry|market|exchange)\b", expression, re.I))),
        }
    functions = re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(", expression)
    return {
        "functions": [item.lower() for item in functions],
        "windows": re.findall(r"\b(?:ts_[A-Za-z_]+|delay|delta)\s*\([^)]*,\s*(\d+)", expression),
        "groups": sorted(set(re.findall(r"\b(industry|sector|subindustry|market|exchange)\b", expression, re.I))),
    }


def _structure_similarity(left: dict[str, Any], right: dict[str, Any]) -> float:
    lf = [str(item).lower() for item in left.get("functions", [])]
    rf = [str(item).lower() for item in right.get("functions", [])]
    lw = [str(item) for item in left.get("windows", [])]
    rw = [str(item) for item in right.get("windows", [])]
    lg = [str(item).lower() for item in left.get("groups", [])]
    rg = [str(item).lower() for item in right.get("groups", [])]
    score = _sequence_overlap(lf, rf) * 0.55 + _counter_overlap(lf, rf) * 0.15
    score += _sequence_overlap(lw, rw) * 0.15 + _sequence_overlap(lg, rg) * 0.15
    return round(max(0.0, min(1.0, score)), 6)


def _sequence_overlap(left: list[str], right: list[str]) -> float:
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    return difflib.SequenceMatcher(None, left, right).ratio()


def _counter_overlap(left: list[str], right: list[str]) -> float:
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    left_counter = Counter(left)
    right_counter = Counter(right)
    overlap = sum(min(left_counter[key], right_counter[key]) for key in set(left_counter) | set(right_counter))
    total = max(sum(left_counter.values()), sum(right_counter.values()), 1)
    return overlap / total
