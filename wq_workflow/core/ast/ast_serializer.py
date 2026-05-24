from __future__ import annotations

from typing import Any

from .ast_node import ASTNode

WINDOW_OPERATORS = {
    "ts_backfill",
    "ts_corr",
    "ts_count_nans",
    "ts_decay_exp_window",
    "ts_delta",
    "ts_mean",
    "ts_product",
    "ts_rank",
    "ts_scale",
    "ts_std_dev",
    "ts_sum",
    "ts_zscore",
}


def serialize_ast(ast: ASTNode) -> str:
    if ast.type == "program":
        return "\n".join(serialize_ast(child) for child in ast.children)
    if ast.type == "assignment":
        return f"{ast.name} = {serialize_ast(ast.children[0])}" if ast.children else f"{ast.name} ="
    if ast.type == "operator":
        args = [serialize_ast(child) for child in ast.children]
        for key, value in ast.parameters.items():
            if key == "window" and ast.name in WINDOW_OPERATORS:
                args.append(_format_value(value))
            else:
                args.append(_format_parameter(key, value))
        return f"{ast.name}({', '.join(args)})"
    if ast.type == "field":
        return ast.name
    if ast.type == "variable":
        return ast.name
    if ast.type == "number":
        return _format_number(ast.value)
    if ast.type == "string":
        return _quote(str(ast.value))
    if ast.type == "unary":
        return f"{ast.operator}{serialize_ast(ast.children[0])}" if ast.children else ast.operator
    if ast.type == "binary":
        left = serialize_ast(ast.children[0]) if ast.children else ""
        right = serialize_ast(ast.children[1]) if len(ast.children) > 1 else ""
        return f"{left} {ast.operator} {right}".strip()
    if ast.type == "comparison":
        left = serialize_ast(ast.children[0]) if ast.children else ""
        right = serialize_ast(ast.children[1]) if len(ast.children) > 1 else ""
        return f"{left} {ast.operator} {right}".strip()
    return ast.name or str(ast.value or "")


def _format_parameter(key: str, value: Any) -> str:
    if isinstance(value, ASTNode):
        return f"{key}={serialize_ast(value)}"
    if isinstance(value, str):
        return f"{key}={_quote(value)}"
    return f"{key}={_format_number(value)}" if isinstance(value, (int, float)) else f"{key}={value}"


def _format_value(value: Any) -> str:
    if isinstance(value, ASTNode):
        return serialize_ast(value)
    if isinstance(value, str):
        return _quote(value)
    return _format_number(value) if isinstance(value, (int, float)) else str(value)


def _format_number(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
