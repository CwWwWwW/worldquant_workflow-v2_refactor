from __future__ import annotations

import difflib
import math
from collections import Counter
from typing import Any

from .ast import ASTNode, walk
from .mutation_constraints import ast_depth
from .operators import OPERATOR_EMBEDDINGS, field_category
from .parser import ExpressionParser, ParseError


class SemanticSimilarity:
    def __init__(self, duplicate_threshold: float = 0.85) -> None:
        self.duplicate_threshold = duplicate_threshold
        self.parser = ExpressionParser()

    def similarity(self, left_ast: ASTNode, right_ast: ASTNode, metrics: dict[str, Any] | None = None) -> float:
        return self.ast_similarity(left_ast, right_ast, metrics)

    def ast_similarity(self, left_ast: ASTNode, right_ast: ASTNode, metrics: dict[str, Any] | None = None) -> float:
        scores = {
            "operator_sequence": _sequence_similarity(operator_sequence(left_ast), operator_sequence(right_ast)),
            "operator_distribution": self.operator_distribution_similarity(left_ast, right_ast),
            "signal_semantic": self.signal_semantic_similarity(left_ast, right_ast),
            "graph_distance": 1.0 - self.graph_distance(left_ast, right_ast),
            "nesting": _depth_similarity(left_ast, right_ast),
            "neutralization": _sequence_similarity(neutralization_structure(left_ast), neutralization_structure(right_ast)),
            "time_series": _sequence_similarity(time_series_structure(left_ast), time_series_structure(right_ast)),
        }
        weighted = (
            scores["operator_sequence"] * 0.24
            + scores["operator_distribution"] * 0.18
            + scores["signal_semantic"] * 0.18
            + scores["graph_distance"] * 0.14
            + scores["nesting"] * 0.10
            + scores["neutralization"] * 0.08
            + scores["time_series"] * 0.08
        )
        return round(max(0.0, min(1.0, weighted)), 6)

    def operator_distribution_similarity(self, left_ast: ASTNode, right_ast: ASTNode) -> float:
        return _counter_cosine(Counter(operator_sequence(left_ast)), Counter(operator_sequence(right_ast)))

    def signal_semantic_similarity(self, left_ast: ASTNode, right_ast: ASTNode) -> float:
        left = signal_categories(left_ast)
        right = signal_categories(right_ast)
        if not left and not right:
            return 1.0
        return _jaccard(set(left), set(right))

    def graph_distance(self, left_ast: ASTNode, right_ast: ASTNode) -> float:
        left_edges = operator_edges(left_ast)
        right_edges = operator_edges(right_ast)
        if not left_edges and not right_edges:
            return 0.0
        return 1.0 - _jaccard(left_edges, right_edges)

    def is_duplicate(self, expression: str, existing: list[str], threshold: float | None = None) -> tuple[bool, float]:
        cutoff = self.duplicate_threshold if threshold is None else threshold
        try:
            current = self.parser.parse(expression)
        except ParseError:
            return False, 0.0
        best = 0.0
        for row in existing:
            try:
                other = self.parser.parse(row)
            except ParseError:
                continue
            best = max(best, self.similarity(current, other))
            if best > cutoff:
                return True, best
        return False, best


def operator_sequence(ast: ASTNode) -> list[str]:
    return [node.name for node in walk(ast) if node.type == "operator"]


def operator_edges(ast: ASTNode) -> set[tuple[str, str]]:
    edges: set[tuple[str, str]] = set()
    for node in walk(ast):
        if node.type != "operator":
            continue
        for child in node.children:
            if child.type == "operator":
                edges.add((node.name, child.name))
    return edges


def signal_categories(ast: ASTNode) -> list[str]:
    categories = []
    for node in walk(ast):
        if node.type == "field":
            categories.append(field_category(node.name))
        elif node.type == "operator":
            tags = OPERATOR_EMBEDDINGS.get(node.name, set())
            categories.extend(tags)
    return categories


def neutralization_structure(ast: ASTNode) -> list[str]:
    return [node.name for node in walk(ast) if node.type == "operator" and node.name.startswith("group_")]


def time_series_structure(ast: ASTNode) -> list[str]:
    return [node.name for node in walk(ast) if node.type == "operator" and node.name.startswith("ts_")]


def semantic_signature(ast: ASTNode) -> dict[str, Any]:
    return {
        "operators": operator_sequence(ast),
        "operator_edges": [list(edge) for edge in sorted(operator_edges(ast))],
        "signal_categories": sorted(set(signal_categories(ast))),
        "neutralization": neutralization_structure(ast),
        "time_series": time_series_structure(ast),
        "windows": [
            node.parameters.get("window")
            for node in walk(ast)
            if node.type == "operator" and isinstance(node.parameters.get("window"), int)
        ],
        "depth": ast_depth(ast),
    }


def _sequence_similarity(left: list[str], right: list[str]) -> float:
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    return difflib.SequenceMatcher(None, left, right).ratio()


def _counter_cosine(left: Counter[str], right: Counter[str]) -> float:
    if not left and not right:
        return 1.0
    keys = set(left) | set(right)
    numerator = sum(left[key] * right[key] for key in keys)
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    if not left_norm or not right_norm:
        return 0.0
    return numerator / (left_norm * right_norm)


def _jaccard(left: set[Any], right: set[Any]) -> float:
    if not left and not right:
        return 1.0
    return len(left & right) / max(len(left | right), 1)


def _depth_similarity(left_ast: ASTNode, right_ast: ASTNode) -> float:
    left = ast_depth(left_ast)
    right = ast_depth(right_ast)
    return 1.0 - abs(left - right) / max(left, right, 1)
