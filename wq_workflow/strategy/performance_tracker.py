from __future__ import annotations

import statistics
from typing import Any

from wq_workflow.data.json_utils import json_loads_safe, safe_float


class PerformanceTracker:
    def __init__(self, repositories: Any, config: Any, logger: Any | None = None) -> None:
        self.repositories = repositories
        self.config = config
        self.logger = logger

    def update_strategy_performance(self, strategy_id: str | None = None, window_name: str = "recent") -> dict:
        repo = getattr(self.repositories, "strategy", None)
        decision_repo = getattr(self.repositories, "decision", None)
        if repo is None:
            return {"updated": False, "reason": "strategy_repository_unavailable"}
        sid = strategy_id or "legacy_champion"
        decisions = repo.list_strategy_decisions(strategy_id=sid, limit=int(getattr(self.config, "rollback_window_size", 100) or 100))
        outcome_by_alpha: dict[str, dict[str, Any]] = {}
        if decision_repo is not None:
            for outcome in decision_repo.list_outcomes(limit=5000):
                alpha = str(outcome.get("alpha_id") or "")
                if alpha and alpha not in outcome_by_alpha:
                    outcome_by_alpha[alpha] = outcome
        outcomes = [outcome_by_alpha.get(str(d.get("alpha_id") or "")) for d in decisions]
        outcomes = [o for o in outcomes if isinstance(o, dict)]
        metrics = self._metrics(outcomes)
        record = {"strategy_id": sid, "window_name": window_name, **metrics, "performance": metrics}
        record_id = repo.insert_performance(record)
        return {"updated": True, "record_id": record_id, "metrics": metrics}

    def evaluate_recent_window(self, strategy_id: str | None = None) -> dict:
        metrics = self.load_strategy_metrics(strategy_id or "legacy_champion")
        if metrics:
            return metrics
        return self.update_strategy_performance(strategy_id).get("metrics", {})

    def compare_champion_vs_challenger(self, champion_id: str = "legacy_champion", challenger_id: str | None = None) -> dict:
        champ = self.load_strategy_metrics(champion_id) or {}
        chall = self.load_strategy_metrics(challenger_id or "") or {}
        return {
            "champion": champ,
            "challenger": chall,
            "reward_delta": safe_float(chall.get("avg_reward"), 0.0) - safe_float(champ.get("avg_reward"), 0.0),
            "failure_rate_delta": safe_float(chall.get("failure_rate"), 0.0) - safe_float(champ.get("failure_rate"), 0.0),
            "sc_risk_delta": safe_float(chall.get("avg_platform_sc_abs_max"), 0.0) - safe_float(champ.get("avg_platform_sc_abs_max"), 0.0),
        }

    def load_strategy_metrics(self, strategy_id: str) -> dict:
        repo = getattr(self.repositories, "strategy", None)
        if repo is None or not strategy_id:
            return {}
        row = repo.latest_performance(strategy_id)
        if not row:
            return {}
        perf = json_loads_safe(row.get("performance_json"), {})
        data = dict(perf) if isinstance(perf, dict) else {}
        data.update({k: row.get(k) for k in ("sample_count", "avg_reward", "median_reward", "success_rate", "failure_rate", "avg_platform_sc_abs_max", "avg_turnover", "avg_fitness") if k in row})
        return data

    def _metrics(self, outcomes: list[dict[str, Any]]) -> dict:
        rewards = [safe_float(o.get("reward_delta", o.get("reward")), 0.0) for o in outcomes]
        successes = [1.0 if o.get("success") in {1, True} else 0.0 for o in outcomes]
        sc = [safe_float(o.get("platform_sc_abs_max"), 0.0) for o in outcomes]
        turnovers = []
        fitness = []
        for outcome in outcomes:
            metrics = json_loads_safe(outcome.get("metrics_json"), {})
            if isinstance(metrics, dict):
                turnovers.append(safe_float(metrics.get("turnover"), 0.0))
                fitness.append(safe_float(metrics.get("fitness"), 0.0))
        n = len(outcomes)
        return {
            "sample_count": n,
            "avg_reward": sum(rewards) / n if n else 0.0,
            "median_reward": statistics.median(rewards) if rewards else 0.0,
            "success_rate": sum(successes) / n if n else 0.0,
            "failure_rate": 1.0 - (sum(successes) / n) if n else 0.0,
            "avg_platform_sc_abs_max": sum(sc) / n if n else 0.0,
            "avg_turnover": sum(turnovers) / len(turnovers) if turnovers else 0.0,
            "avg_fitness": sum(fitness) / len(fitness) if fitness else 0.0,
        }
