from __future__ import annotations

from typing import Any


class ExperimentPlanner:
    def __init__(self, *, config: Any | None = None) -> None:
        self.config = config

    def plan(self, parent: dict[str, Any] | None = None, alpha_repr: Any | None = None, strategy: dict[str, Any] | None = None) -> dict[str, Any] | None:
        if not getattr(self.config, "enable_experiment_design", False):
            return None
        return {"experiment_type": "parameter_sweep", "base_alpha_id": (parent or {}).get("alpha_id", ""), "controlled_variable": "window", "variants": [], "hypothesis": "first-stage metadata only; candidate generation unchanged", "strategy_id": (strategy or {}).get("strategy_id", "legacy_champion")}
