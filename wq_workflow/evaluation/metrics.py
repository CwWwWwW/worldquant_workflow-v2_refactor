from __future__ import annotations

from typing import Any


def metrics_from_simulation(simulation_result: Any) -> dict[str, Any]:
    if isinstance(simulation_result, dict):
        return dict(simulation_result.get("metrics") or simulation_result)
    return dict(getattr(simulation_result, "metrics", {}) or {})
