from __future__ import annotations

from typing import Any


class BudgetAllocator:
    def __init__(self, config: Any, logger: Any | None = None) -> None:
        self.config = config
        self.logger = logger

    def allocate(self, strategies: list[dict]) -> dict[str, float]:
        rows = [s for s in strategies or [] if isinstance(s, dict)]
        ids = [str(s.get("strategy_id") or "") for s in rows if s.get("strategy_id")]
        champion = next((s for s in rows if s.get("role") == "champion" and s.get("status", "active") == "active"), None)
        champion_id = str((champion or {}).get("strategy_id") or getattr(self.config, "strategy_default_champion", "legacy_champion") or "legacy_champion")
        out = {sid: 0.0 for sid in ids}
        out.setdefault(champion_id, 0.0)
        if not getattr(self.config, "enable_strategy_portfolio", True):
            out[champion_id] = 1.0
            return self._normalize(out, champion_id)
        if not getattr(self.config, "enable_challenger_live_budget", False):
            out[champion_id] = 1.0
            return self._normalize(out, champion_id)

        challenger_budget = max(0.0, min(1.0, float(getattr(self.config, "strategy_challenger_live_budget", 0.0) or 0.0)))
        baseline_budget = max(0.0, min(1.0, float(getattr(self.config, "strategy_random_baseline_budget", 0.0) or 0.0)))
        if challenger_budget + baseline_budget > 1.0:
            scale = 1.0 / (challenger_budget + baseline_budget)
            challenger_budget *= scale
            baseline_budget *= scale
        safe_challengers = [
            s for s in rows
            if s.get("role") == "challenger"
            and s.get("status", "active") == "active"
            and bool(s.get("safety_pass") or s.get("safety_status") in {"pass", "passed", "safe"})
        ]
        out[champion_id] = max(0.0, 1.0 - challenger_budget - baseline_budget)
        share = challenger_budget / len(safe_challengers) if safe_challengers else 0.0
        for strategy in safe_challengers:
            out[str(strategy.get("strategy_id"))] = share
        if "random_baseline" in out:
            out["random_baseline"] = baseline_budget
        else:
            out["random_baseline"] = baseline_budget
        if not safe_challengers:
            out[champion_id] += challenger_budget
        return self._normalize(out, champion_id)

    def _normalize(self, allocations: dict[str, float], champion_id: str) -> dict[str, float]:
        total = sum(max(0.0, float(v or 0.0)) for v in allocations.values())
        if total <= 0:
            return {**{k: 0.0 for k in allocations}, champion_id: 1.0}
        normalized = {k: max(0.0, float(v or 0.0)) / total for k, v in allocations.items()}
        drift = 1.0 - sum(normalized.values())
        normalized[champion_id] = max(0.0, normalized.get(champion_id, 0.0) + drift)
        return normalized
