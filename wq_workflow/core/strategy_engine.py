from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from ..safe_io import finite_float


class StrategyType(str, Enum):
    SHARPE_OPTIMIZATION = "sharpe_optimization"
    FITNESS_REPAIR = "fitness_repair"
    TURNOVER_REDUCTION = "turnover_reduction"
    SIMPLIFICATION = "simplification"
    DIVERSITY_EXPANSION = "diversity_expansion"


@dataclass
class Strategy:
    name: StrategyType
    allowed_mutations: list[str]
    forbidden_mutations: list[str] = field(default_factory=list)
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name.value,
            "allowed_mutations": self.allowed_mutations,
            "forbidden_mutations": self.forbidden_mutations,
            "reason": self.reason,
        }


class StrategyEngine:
    def choose(
        self,
        metrics: dict[str, float] | None,
        history: list[dict[str, Any]] | None = None,
        failures: list[dict[str, Any]] | None = None,
    ) -> Strategy:
        metrics = metrics or {}
        history = history or []
        failures = failures or []
        turnover = _float(metrics.get("turnover"))
        sharpe = _float(metrics.get("sharpe"))
        fitness = _float(metrics.get("fitness"))

        if turnover > 65:
            return Strategy(
                StrategyType.TURNOVER_REDUCTION,
                ["wrap_node", "replace_window", "simplify_branch"],
                ["replace_field", "replace_core_signal"],
                "turnover is above threshold",
            )
        if self._stagnant(history, "sharpe") or _failure_mentions(failures, "duplicate"):
            return Strategy(
                StrategyType.DIVERSITY_EXPANSION,
                ["replace_operator", "wrap_node", "replace_window", "insert_node"],
                ["full_rewrite"],
                "sharpe is stagnant or candidates are converging",
            )
        if fitness < 1.0 and sharpe >= 0.8:
            return Strategy(
                StrategyType.FITNESS_REPAIR,
                ["wrap_node", "replace_operator", "replace_window"],
                ["replace_core_signal"],
                "fitness below threshold while sharpe is usable",
            )
        if sharpe < 0.8:
            return Strategy(
                StrategyType.SHARPE_OPTIMIZATION,
                ["simplify_branch", "replace_operator", "replace_window", "wrap_node"],
                ["full_rewrite"],
                "sharpe below threshold",
            )
        return Strategy(
            StrategyType.SIMPLIFICATION,
            ["simplify_branch", "remove_node", "replace_window"],
            ["increase_depth"],
            "quality needs controlled simplification",
        )

    def _stagnant(self, history: list[dict[str, Any]], metric: str) -> bool:
        if len(history) < 4:
            return False
        values = [_float(row.get("metrics_after", {}).get(metric, row.get("metrics", {}).get(metric))) for row in history[-4:]]
        return max(values) - min(values) < 0.05


def _failure_mentions(failures: list[dict[str, Any]], pattern: str) -> bool:
    return any(pattern in str(row).lower() for row in failures[-5:])


def _float(value: Any) -> float:
    return finite_float(value)
