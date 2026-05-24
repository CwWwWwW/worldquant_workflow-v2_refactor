from __future__ import annotations

from dataclasses import dataclass, field

from .ast import ASTNode, walk
from .operators import ILLEGAL_NESTING, NEUTRALIZATION_OPERATORS


@dataclass
class ConstraintResult:
    passed: bool
    reason: str = ""
    details: dict[str, int | str] = field(default_factory=dict)


@dataclass
class MutationConstraints:
    max_depth: int = 8
    max_operator_count: int = 24
    max_neutralization_layers: int = 2
    duplicate_rank_allowed: bool = False

    def validate(self, ast: ASTNode) -> ConstraintResult:
        depth = ast_depth(ast)
        operators = operator_count(ast)
        neutralizations = sum(
            1 for node in walk(ast) if node.type == "operator" and node.name in NEUTRALIZATION_OPERATORS
        )
        if depth > self.max_depth:
            return ConstraintResult(False, f"nesting depth {depth} exceeds {self.max_depth}", {"depth": depth})
        if operators > self.max_operator_count:
            return ConstraintResult(
                False,
                f"operator count {operators} exceeds {self.max_operator_count}",
                {"operator_count": operators},
            )
        if neutralizations > self.max_neutralization_layers:
            return ConstraintResult(
                False,
                "too many neutralization layers",
                {"neutralization_layers": neutralizations},
            )
        illegal = first_illegal_nesting(ast)
        if illegal:
            return ConstraintResult(False, illegal)
        return ConstraintResult(True, "", {"depth": depth, "operator_count": operators})


def ast_depth(ast: ASTNode) -> int:
    if not ast.children:
        return 0 if ast.type in {"field", "variable", "number", "string"} else 1
    return 1 + max(ast_depth(child) for child in ast.children)


def operator_count(ast: ASTNode) -> int:
    return sum(1 for node in walk(ast) if node.type == "operator")


def parameter_windows(ast: ASTNode) -> list[int]:
    values: list[int] = []
    for node in walk(ast):
        value = node.parameters.get("window") if node.type == "operator" else None
        if isinstance(value, int):
            values.append(value)
    return values


def ts_operator_count(ast: ASTNode) -> int:
    return sum(1 for node in walk(ast) if node.type == "operator" and node.name.startswith("ts_"))


def neutralization_layers(ast: ASTNode) -> int:
    return sum(1 for node in walk(ast) if node.type == "operator" and node.name in NEUTRALIZATION_OPERATORS)


def first_illegal_nesting(ast: ASTNode) -> str:
    for node in walk(ast):
        if node.type != "operator":
            continue
        for child in node.children:
            if child.type != "operator":
                continue
            reason = ILLEGAL_NESTING.get((node.name, child.name))
            if reason:
                return reason
    return ""
