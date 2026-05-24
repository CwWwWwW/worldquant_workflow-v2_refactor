from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .ast import ASTNode
from .operators import BAD_COMBINATIONS
from .semantic_similarity import operator_edges
from ..safe_io import finite_float


@dataclass
class OperatorEdgeStats:
    count: int = 0
    success_count: int = 0
    reward_sum: float = 0.0

    @property
    def success_rate(self) -> float:
        return self.success_count / max(self.count, 1)

    def to_dict(self) -> dict[str, float | int]:
        return {
            "count": self.count,
            "success_count": self.success_count,
            "success_rate": round(self.success_rate, 6),
            "avg_reward": round(self.reward_sum / max(self.count, 1), 6),
        }


class OperatorGraph:
    def __init__(self) -> None:
        self.edges: dict[tuple[str, str], OperatorEdgeStats] = {}
        self.bad_combinations = dict(BAD_COMBINATIONS)

    def record(self, ast: ASTNode, *, reward: float = 0.0, success: bool = False) -> None:
        for edge in operator_edges(ast):
            stats = self.edges.setdefault(edge, OperatorEdgeStats())
            stats.count += 1
            stats.reward_sum += finite_float(reward)
            if success:
                stats.success_count += 1

    def recommendations(self, ast: ASTNode | None = None, limit: int = 5) -> list[str]:
        ranked = sorted(self.edges.items(), key=lambda item: (item[1].success_rate, item[1].reward_sum), reverse=True)
        lines = [f"{left} -> {right}: success_rate={stats.success_rate:.2f}" for (left, right), stats in ranked[:limit]]
        return lines or ["No operator graph recommendation yet."]

    def should_avoid(self, parent: str, child: str) -> bool:
        key = f"{parent}({child}())"
        return key in self.bad_combinations

    def to_dict(self) -> dict[str, Any]:
        return {f"{left} -> {right}": stats.to_dict() for (left, right), stats in sorted(self.edges.items())}

    @classmethod
    def from_statistics(cls, statistics: dict[str, Any]) -> "OperatorGraph":
        graph = cls()
        for key, value in statistics.items():
            if "->" not in key or not isinstance(value, dict):
                continue
            left, right = [part.strip() for part in key.split("->", 1)]
            stats = graph.edges.setdefault((left, right), OperatorEdgeStats())
            stats.count = int(value.get("count", 0) or 0)
            rate = finite_float(value.get("success_rate", 0.0))
            stats.success_count = int(round(stats.count * rate))
            stats.reward_sum = finite_float(value.get("avg_reward", 0.0)) * max(stats.count, 1)
        return graph
