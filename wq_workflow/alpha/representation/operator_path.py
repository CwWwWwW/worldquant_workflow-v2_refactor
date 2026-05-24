from __future__ import annotations

from typing import Any

from .ast import AlphaASTNode


TS_OPERATORS = {"ts_rank", "ts_mean", "ts_std_dev", "ts_delta", "delay", "delta", "decay_linear", "ts_sum", "ts_min", "ts_max"}
RANK_OPERATORS = {"rank", "ts_rank", "zscore", "scale"}
GROUP_OPERATORS = {"group_neutralize", "group_rank", "group_zscore", "group_mean"}
TRADE_OPERATORS = {"trade_when", "if_else"}
VECTOR_OPERATORS = {"vec_avg", "vec_sum", "vec_max", "vec_min"}
ARITHMETIC_OPERATORS = {"add", "subtract", "multiply", "divide", "signed_power", "log", "abs"}


def extract_operator_sequence(ast: AlphaASTNode | None) -> list[str]:
    return ast.operators() if ast is not None else []


def extract_operator_bigrams(operators: list[str]) -> list[str]:
    return [f"{operators[i]}>{operators[i + 1]}" for i in range(max(0, len(operators) - 1))]


def extract_operator_trigrams(operators: list[str]) -> list[str]:
    return [f"{operators[i]}>{operators[i + 1]}>{operators[i + 2]}" for i in range(max(0, len(operators) - 2))]


def extract_leaf_fields(ast: AlphaASTNode | None) -> list[str]:
    if ast is None:
        return []
    return [n.value for n in ast.walk() if n.node_type == "field" and not n.children]


def extract_path_to_fields(ast: AlphaASTNode | None) -> dict[str, list[str]]:
    paths: dict[str, list[str]] = {}

    def visit(node: AlphaASTNode, stack: list[str]) -> None:
        next_stack = stack + ([node.value] if node.node_type == "operator" else [])
        if node.node_type == "field":
            paths.setdefault(node.value, []).append(">".join(next_stack + [node.value]))
        for child in node.children:
            visit(child, next_stack)

    if ast is not None:
        visit(ast, [])
    return paths


def _operator_depth_map(ast: AlphaASTNode | None) -> dict[str, int]:
    out: dict[str, int] = {}
    if ast is None:
        return out
    for node in ast.walk():
        if node.node_type == "operator":
            out[node.value] = min(node.depth, out.get(node.value, node.depth))
    return out


def operator_path_features(ast: AlphaASTNode | None) -> dict[str, Any]:
    operators = extract_operator_sequence(ast)
    root = ast.value if ast is not None and ast.node_type == "operator" else ""
    return {
        "root_operator": root,
        "operator_sequence": operators,
        "operator_bigrams": extract_operator_bigrams(operators),
        "operator_trigrams": extract_operator_trigrams(operators),
        "operator_depth_map": _operator_depth_map(ast),
        "leaf_fields": extract_leaf_fields(ast),
        "path_to_fields": extract_path_to_fields(ast),
        "ts_operator_count": sum(1 for op in operators if op in TS_OPERATORS or op.startswith("ts_")),
        "group_operator_count": sum(1 for op in operators if op in GROUP_OPERATORS or op.startswith("group_")),
        "rank_operator_count": sum(1 for op in operators if op in RANK_OPERATORS),
        "vector_operator_count": sum(1 for op in operators if op in VECTOR_OPERATORS or op.startswith("vec_")),
        "arithmetic_operator_count": sum(1 for op in operators if op in ARITHMETIC_OPERATORS),
        "trade_operator_count": sum(1 for op in operators if op in TRADE_OPERATORS),
    }
