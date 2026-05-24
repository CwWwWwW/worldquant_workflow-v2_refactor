from __future__ import annotations

import random
from typing import Any

from ...core.ast import ASTNode, serialize_ast
from ...core.parser import ExpressionParser, ParseError
from .authority import evolution_authority
from .ast_evolution_engine import ASTEvolutionEngine, ASTEvolutionResult


class ASTCrossover:
    def __init__(
        self,
        engine: ASTEvolutionEngine | None = None,
        config: Any | None = None,
        random_seed: int | None = None,
        graph: Any | None = None,
    ) -> None:
        self.engine = engine or ASTEvolutionEngine()
        self.config = config
        self.graph = graph
        if random_seed is None:
            random_seed = getattr(config, "crossover_random_seed", None)
        self._rng = random.Random(random_seed)

    def crossover(self, parent_a: str, parent_b: str) -> ASTEvolutionResult:
        try:
            ast_a = ExpressionParser().parse(parent_a)
            ast_b = ExpressionParser().parse(parent_b)
        except ParseError as exc:
            return self.engine.rollback(parent_a, operation="crossover", reason=str(exc))

        attempts = max(1, int(getattr(self.config, "max_crossover_attempts", 5) or 5))
        random_enabled = bool(getattr(self.config, "crossover_random_subtree_selection", True))
        last_reason = "no_valid_crossover"
        for attempt in range(attempts):
            path_a = self._choose_subtree_path(ast_a, "receiver") if random_enabled else _first_replaceable_path(ast_a)[0]
            path_b = self._choose_subtree_path(ast_b, "donor") if random_enabled else _first_replaceable_path(ast_b)[0]
            if path_a is None or path_b is None:
                last_reason = "no replaceable subtree"
                continue
            try:
                node_b = _get_path(ast_b, path_b)
            except Exception as exc:
                last_reason = str(exc)
                continue
            clone = ast_a.clone()
            _replace_path(clone, path_a, node_b)
            expression = serialize_ast(clone)
            reason = self.engine.validate_ast(clone, expression)
            if reason:
                last_reason = reason
                continue
            return ASTEvolutionResult(
                expression=expression,
                ok=True,
                metadata={
                    "operation": "crossover",
                    "donor_expression": parent_b,
                    "attempt": attempt + 1,
                    "path_a": list(path_a),
                    "path_b": list(path_b),
                    "selection": "random_subtree" if random_enabled else "first_replaceable",
                    **evolution_authority(self.config, "crossover", active_decision=True),
                },
            )
        return self.engine.rollback(
            parent_a,
            operation="crossover",
            reason=last_reason,
            metadata={"donor_expression": parent_b, "attempts": attempts, "selection": "random_subtree" if random_enabled else "first_replaceable"},
        )

    def _replaceable_paths(self, ast: ASTNode) -> list[tuple[int, ...]]:
        return [path for path, node in _paths(ast) if path and node.type in {"operator", "field", "variable", "binary", "comparison"}] or [()]

    def _choose_subtree_path(self, ast: ASTNode, role: str = "receiver", context: dict[str, Any] | None = None) -> tuple[int, ...] | None:
        paths = self._replaceable_paths(ast)
        if not paths:
            return None
        if self.graph is not None and bool(getattr(self.config, "crossover_use_graph_bias", False)):
            weighted = self._weight_paths_by_graph(ast, paths, role=role, context=context)
            choice = self._weighted_choice_path(weighted)
            if choice is not None:
                return choice
        return self._rng.choice(paths)

    def _weight_paths_by_graph(
        self,
        ast: ASTNode,
        paths: list[tuple[int, ...]],
        role: str = "receiver",
        context: dict[str, Any] | None = None,
    ) -> list[tuple[tuple[int, ...], float]]:
        weighted: list[tuple[tuple[int, ...], float]] = []
        for path in paths:
            try:
                node = _get_path(ast, path)
                weight = 1.0
                if node.type == "operator" and node.name:
                    weight += 0.1
                weighted.append((path, weight))
            except Exception:
                continue
        return weighted

    def _weighted_choice_path(self, weighted: list[tuple[tuple[int, ...], float]]) -> tuple[int, ...] | None:
        if not weighted:
            return None
        total = sum(max(0.0, float(weight)) for _path, weight in weighted)
        if total <= 0:
            return self._rng.choice([path for path, _weight in weighted])
        draw = self._rng.random() * total
        running = 0.0
        for path, weight in weighted:
            running += max(0.0, float(weight))
            if running >= draw:
                return path
        return weighted[-1][0]

    def maybe_crossover(
        self,
        parent_a: dict[str, Any] | None,
        parent_b: dict[str, Any] | None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        if not parent_a or not parent_b:
            return None
        expr_a = str(parent_a.get("expression") or parent_a.get("code") or "")
        expr_b = str(parent_b.get("expression") or parent_b.get("code") or "")
        if not expr_a or not expr_b:
            return None
        result = self.crossover(expr_a, expr_b)
        if not result.ok:
            return None
        family = str(parent_a.get("behavior_family") or parent_a.get("family") or "unknown")
        parent_a_id = str(parent_a.get("alpha_id") or parent_a.get("alpha_name") or "")
        parent_b_id = str(parent_b.get("alpha_id") or parent_b.get("alpha_name") or "")
        return {
            "alpha_id": "",
            "expression": result.expression,
            "parent_ids": [parent_a_id, parent_b_id],
            "parent_reward": float(parent_a.get("reward", parent_a.get("score", 0.0)) or 0.0),
            "family": family,
            "behavior_family": family,
            "lineage_depth": max(
                int(parent_a.get("lineage_depth", 0) or 0),
                int(parent_b.get("lineage_depth", 0) or 0),
            )
            + 1,
            "mutation_type": "crossover",
            "mutation_history": [
                {
                    "type": "crossover",
                    "parent_a": parent_a_id,
                    "parent_b": parent_b_id,
                    "context": context or {},
                    "metadata": result.metadata,
                }
            ],
            "source": "ga_crossover",
            "candidate_source": "crossover",
            "is_pending_candidate": True,
            "metadata": result.metadata,
        }


CrossoverEngine = ASTCrossover


def _first_replaceable_path(ast: ASTNode) -> tuple[tuple[int, ...], ASTNode | None]:
    paths = _paths(ast)
    for path, node in paths:
        if path and node.type in {"operator", "field", "variable", "binary", "comparison"}:
            return path, node
    return (), ast


def _paths(ast: ASTNode, path: tuple[int, ...] = ()) -> list[tuple[tuple[int, ...], ASTNode]]:
    rows = [(path, ast)]
    for index, child in enumerate(ast.children):
        rows.extend(_paths(child, path + (index,)))
    return rows


def _get_path(ast: ASTNode, path: tuple[int, ...]) -> ASTNode:
    node = ast
    for index in path:
        node = node.children[index]
    return node


def _replace_path(ast: ASTNode, path: tuple[int, ...], replacement: ASTNode) -> None:
    if not path:
        ast.type = replacement.type
        ast.name = replacement.name
        ast.operator = replacement.operator
        ast.children = [child.clone() for child in replacement.children]
        ast.parameters = dict(replacement.parameters)
        ast.metadata = dict(replacement.metadata)
        ast.value = replacement.value
        return
    parent = _get_path(ast, path[:-1])
    parent.children[path[-1]] = replacement.clone()
