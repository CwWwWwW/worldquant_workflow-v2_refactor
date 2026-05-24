from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .ast import ASTNode
from .mutation_constraints import MutationConstraints
from .semantic_similarity import SemanticSimilarity
from .structural_mutator import MutationCandidate, StructuralMutator
from ..safe_io import finite_float


@dataclass
class EvolutionNode:
    expression: str
    ast: ASTNode
    reward: float = 0.0
    parent: "EvolutionNode | None" = None
    children: list["EvolutionNode"] = field(default_factory=list)
    mutation_type: str = ""
    depth: int = 0
    metrics: dict[str, float] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


class EvolutionTree:
    def __init__(
        self,
        mutator: StructuralMutator | None = None,
        similarity: SemanticSimilarity | None = None,
        constraints: MutationConstraints | None = None,
    ) -> None:
        self.mutator = mutator or StructuralMutator()
        self.similarity = similarity or SemanticSimilarity()
        self.constraints = constraints or MutationConstraints()
        self.nodes: list[EvolutionNode] = []

    def add_root(self, expression: str, ast: ASTNode, metrics: dict[str, float] | None = None) -> EvolutionNode:
        node = EvolutionNode(expression=expression, ast=ast, metrics=metrics or {})
        self.nodes.append(node)
        return node

    def expand(self, parents: list[EvolutionNode], beam_width: int = 8, strategy: object | None = None) -> list[EvolutionNode]:
        beam_width = min(max(int(beam_width), 5), 20)
        candidates: list[EvolutionNode] = []
        for parent in parents:
            parent_candidates: list[EvolutionNode] = []
            mutations = self.mutator.generate(parent.ast, strategy, self.constraints)
            for candidate in mutations:
                if self._too_similar(candidate, candidates) and parent_candidates:
                    continue
                child = EvolutionNode(
                    expression=candidate.expression,
                    ast=candidate.ast,
                    parent=parent,
                    mutation_type=candidate.mutation_type,
                    depth=parent.depth + 1,
                    metadata={"description": candidate.description},
                )
                parent.children.append(child)
                parent_candidates.append(child)
                candidates.append(child)
        selected = self._select_beam(candidates, beam_width)
        self.nodes.extend(selected)
        return selected

    def _too_similar(self, candidate: MutationCandidate, selected: list[EvolutionNode]) -> bool:
        for node in selected:
            if self.similarity.similarity(candidate.ast, node.ast) > self.similarity.duplicate_threshold:
                return True
        return False

    def _select_beam(self, nodes: list[EvolutionNode], beam_width: int) -> list[EvolutionNode]:
        if len(nodes) <= beam_width:
            return nodes
        selected: list[EvolutionNode] = []
        selectors = [
            lambda row: row.reward,
            lambda row: _diversity_proxy(row, nodes),
            lambda row: -_turnover(row),
            lambda row: _recent_improvement(row),
        ]
        for selector in selectors:
            best = max(nodes, key=selector)
            if best not in selected:
                selected.append(best)
        remaining = [node for node in nodes if node not in selected]
        remaining.sort(key=lambda row: row.reward + _diversity_proxy(row, nodes) * 0.2 - _turnover(row) * 0.005, reverse=True)
        selected.extend(remaining[: max(0, beam_width - len(selected))])
        return selected[:beam_width]


def _turnover(node: EvolutionNode) -> float:
    return finite_float(node.metrics.get("turnover", 0.0))


def _recent_improvement(node: EvolutionNode) -> float:
    return finite_float(node.metadata.get("recent_improvement", 0.0))


def _diversity_proxy(node: EvolutionNode, nodes: list[EvolutionNode]) -> float:
    if len(nodes) <= 1:
        return 1.0
    similarity = SemanticSimilarity()
    distances = [1.0 - similarity.similarity(node.ast, other.ast) for other in nodes if other is not node]
    return sum(distances) / max(len(distances), 1)
