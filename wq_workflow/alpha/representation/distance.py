from __future__ import annotations

from typing import Any


def _clamp(value: float) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except Exception:
        return 0.0


def jaccard_similarity(a: list[str], b: list[str]) -> float:
    try:
        sa = set(a or [])
        sb = set(b or [])
        if not sa and not sb:
            return 1.0
        if not sa or not sb:
            return 0.0
        return _clamp(len(sa & sb) / len(sa | sb))
    except Exception:
        return 0.0


def expression_jaccard_similarity(rep_a: Any, rep_b: Any) -> float:
    return jaccard_similarity(list(str(getattr(rep_a, "normalized_expression", "") or "")), list(str(getattr(rep_b, "normalized_expression", "") or "")))


def operator_similarity(rep_a: Any, rep_b: Any) -> float:
    return jaccard_similarity(getattr(rep_a, "operator_sequence", []) or [], getattr(rep_b, "operator_sequence", []) or [])


def field_similarity(rep_a: Any, rep_b: Any) -> float:
    return jaccard_similarity(getattr(rep_a, "field_sequence", []) or [], getattr(rep_b, "field_sequence", []) or [])


def subtree_similarity(rep_a: Any, rep_b: Any) -> float:
    return jaccard_similarity(getattr(rep_a, "subtree_fingerprints", []) or [], getattr(rep_b, "subtree_fingerprints", []) or [])


def parameter_similarity(rep_a: Any, rep_b: Any) -> float:
    try:
        a = [float(v) for v in (getattr(rep_a, "numeric_params", []) or [])]
        b = [float(v) for v in (getattr(rep_b, "numeric_params", []) or [])]
        if not a and not b:
            return 1.0
        if not a or not b:
            return 0.0
        limit = min(len(a), len(b))
        diffs = [abs(a[i] - b[i]) / max(abs(a[i]), abs(b[i]), 1.0) for i in range(limit)]
        length_penalty = abs(len(a) - len(b)) / max(len(a), len(b), 1)
        return _clamp(1.0 - ((sum(diffs) / max(limit, 1)) * 0.8 + length_penalty * 0.2))
    except Exception:
        return 0.0


def tree_shape_similarity(rep_a: Any, rep_b: Any) -> float:
    try:
        pairs = (
            ("ast_depth", 0.35),
            ("node_count", 0.25),
            ("operator_count", 0.20),
            ("field_count", 0.20),
        )
        score = 0.0
        for attr, weight in pairs:
            va = float(getattr(rep_a, attr, 0) or 0)
            vb = float(getattr(rep_b, attr, 0) or 0)
            score += weight * (1.0 - abs(va - vb) / max(va, vb, 1.0))
        return _clamp(score)
    except Exception:
        return 0.0


def behavior_similarity(rep_a: Any, rep_b: Any) -> float:
    try:
        if getattr(rep_a, "behavior_fingerprint", "") and getattr(rep_a, "behavior_fingerprint", "") == getattr(rep_b, "behavior_fingerprint", ""):
            return 1.0
        family_match = 1.0 if getattr(rep_a, "behavior_family", "") == getattr(rep_b, "behavior_family", "") else 0.0
        return _clamp(0.6 * family_match + 0.4 * operator_similarity(rep_a, rep_b))
    except Exception:
        return 0.0


def combined_expression_similarity(rep_a: Any, rep_b: Any) -> float:
    try:
        return _clamp(
            0.30 * operator_similarity(rep_a, rep_b)
            + 0.20 * field_similarity(rep_a, rep_b)
            + 0.25 * subtree_similarity(rep_a, rep_b)
            + 0.10 * parameter_similarity(rep_a, rep_b)
            + 0.15 * tree_shape_similarity(rep_a, rep_b)
        )
    except Exception:
        return 0.0


def operator_jaccard_similarity(rep_a: Any, rep_b: Any) -> float:
    return operator_similarity(rep_a, rep_b)


def field_jaccard_similarity(rep_a: Any, rep_b: Any) -> float:
    return field_similarity(rep_a, rep_b)


def subtree_jaccard_similarity(rep_a: Any, rep_b: Any) -> float:
    return subtree_similarity(rep_a, rep_b)


def parameter_distance(rep_a: Any, rep_b: Any) -> float:
    return _clamp(1.0 - parameter_similarity(rep_a, rep_b))


def semantic_similarity(rep_a: Any, rep_b: Any) -> float:
    return behavior_similarity(rep_a, rep_b)


def semantic_distance(rep_a: Any, rep_b: Any) -> float:
    return _clamp(1.0 - semantic_similarity(rep_a, rep_b))
