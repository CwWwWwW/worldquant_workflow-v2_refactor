from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ...core.ast import ASTNode, serialize_ast, walk
from ...core.mutation_constraints import ast_depth, operator_count, ts_operator_count
from ...core.parser import ExpressionParser, ParseError
from ...paths import AST_EVOLUTION_FAILURE_LOG_FILE
from ...safe_io import append_jsonl


MAX_AST_DEPTH = 12
MAX_OPERATOR_COUNT = 40
MAX_EXPR_LENGTH = 512
MAX_NESTED_TS = 5


@dataclass(slots=True)
class ASTEvolutionResult:
    expression: str
    ok: bool
    rolled_back: bool = False
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ASTEvolutionEngine:
    def __init__(
        self,
        *,
        failure_log_path: Path = AST_EVOLUTION_FAILURE_LOG_FILE,
        max_depth: int = MAX_AST_DEPTH,
        max_operator_count: int = MAX_OPERATOR_COUNT,
        max_expression_length: int = MAX_EXPR_LENGTH,
        max_nested_ts: int = MAX_NESTED_TS,
    ) -> None:
        self.failure_log_path = failure_log_path
        self.max_depth = max_depth
        self.max_operator_count = max_operator_count
        self.max_expression_length = max_expression_length
        self.max_nested_ts = max_nested_ts

    def validate_ast(self, ast: ASTNode, expression: str | None = None) -> str:
        text = expression if expression is not None else serialize_ast(ast)
        if ast_depth(ast) > self.max_depth:
            return f"ast depth exceeds {self.max_depth}"
        if operator_count(ast) > self.max_operator_count:
            return f"operator count exceeds {self.max_operator_count}"
        if len(text or "") > self.max_expression_length:
            return f"expression length exceeds {self.max_expression_length}"
        if _nested_ts_depth(ast) > self.max_nested_ts:
            return f"nested ts depth exceeds {self.max_nested_ts}"
        return ""

    def rollback(self, parent_expression: str, *, operation: str, reason: str, metadata: dict[str, Any] | None = None) -> ASTEvolutionResult:
        payload = {
            "version": "1.2.0",
            "operation": operation,
            "reason": reason,
            "parent_fingerprint": _fingerprint(parent_expression),
            "metadata": metadata or {},
        }
        payload["event_id"] = _event_id(payload)
        append_jsonl(self.failure_log_path, payload)
        return ASTEvolutionResult(
            expression=parent_expression,
            ok=False,
            rolled_back=True,
            reason=reason,
            metadata={"failure_event_id": payload["event_id"], **(metadata or {})},
        )

    def parse_parent(self, parent_expression: str, *, operation: str) -> ASTNode | ASTEvolutionResult:
        try:
            return ExpressionParser().parse(parent_expression)
        except ParseError as exc:
            return self.rollback(parent_expression, operation=operation, reason=str(exc))


def _nested_ts_depth(node: ASTNode) -> int:
    child_depth = max((_nested_ts_depth(child) for child in node.children), default=0)
    if node.type == "operator" and node.name.startswith("ts_"):
        return 1 + child_depth
    return child_depth


def _fingerprint(expression: str) -> str:
    normalized = "".join((expression or "").lower().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def _event_id(payload: dict[str, Any]) -> str:
    text = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:20]
