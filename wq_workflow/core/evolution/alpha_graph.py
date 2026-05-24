from __future__ import annotations

import re
from typing import Any

from ...core.ast import walk
from ...core.parser import ExpressionParser, ParseError


class AlphaGraph:
    def __init__(self, repository: Any | None = None) -> None:
        self.repository = repository

    def record_candidate_result(self, candidate: dict[str, Any], reward: float, success: bool) -> None:
        if self.repository is None:
            return
        expression = str(candidate.get("expression") or candidate.get("code") or "")
        operators = self.extract_operators(expression)
        for left, right in zip(operators, operators[1:]):
            self.repository.upsert_graph_edge(
                edge_type="operator_pair",
                src=left,
                dst=right,
                reward=reward,
                success=success,
                payload={"alpha_id": candidate.get("alpha_id")},
            )
        family = str(candidate.get("behavior_family") or candidate.get("family") or "unknown")
        mutation = str(candidate.get("mutation_type") or "unknown")
        self.repository.upsert_graph_edge(
            edge_type="mutation_to_family",
            src=mutation,
            dst=family,
            reward=reward,
            success=success,
            payload={"alpha_id": candidate.get("alpha_id")},
        )
        self.repository.upsert_graph_edge(
            edge_type="family_to_success",
            src=family,
            dst="success" if success else "failure",
            reward=reward,
            success=success,
            payload={"alpha_id": candidate.get("alpha_id")},
        )
        parent_ids = candidate.get("parent_ids") if isinstance(candidate.get("parent_ids"), list) else []
        for parent in parent_ids:
            self.repository.upsert_graph_edge(
                edge_type="parent_to_child",
                src=str(parent),
                dst=str(candidate.get("alpha_id") or ""),
                reward=reward,
                success=success,
                payload={},
            )
        if mutation == "crossover" and len(parent_ids) >= 2:
            self.repository.upsert_graph_edge(
                edge_type="crossover_pair",
                src=str(parent_ids[0]),
                dst=str(parent_ids[1]),
                reward=reward,
                success=success,
                payload={"child": candidate.get("alpha_id")},
            )
        failure_type = str(candidate.get("failure_type") or candidate.get("failure_reason") or "")
        if failure_type and mutation and mutation != "unknown":
            self.repository.upsert_graph_edge(
                edge_type="failure_to_repair",
                src=failure_type[:120],
                dst=mutation,
                reward=reward,
                success=success,
                payload={"alpha_id": candidate.get("alpha_id")},
            )

    def extract_operators(self, expression: str) -> list[str]:
        try:
            ast = ExpressionParser().parse(expression)
            names = [str(node.name or node.operator or "") for node in walk(ast) if getattr(node, "type", "") == "operator"]
            return [name for name in names if name]
        except ParseError:
            return re.findall(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\s*\(", expression or "")
