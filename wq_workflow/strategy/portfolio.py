from __future__ import annotations

import random
from typing import Any


class StrategyPortfolio:
    def __init__(
        self,
        registry: Any | None = None,
        budget_allocator: Any | None = None,
        performance_tracker: Any | None = None,
        promotion_policy: Any | None = None,
        rollback_policy: Any | None = None,
        config: Any | None = None,
        logger: Any | None = None,
        repositories: Any | None = None,
    ) -> None:
        self.registry = registry
        self.budget_allocator = budget_allocator
        self.performance_tracker = performance_tracker
        self.promotion_policy = promotion_policy
        self.rollback_policy = rollback_policy
        self.config = config
        self.logger = logger
        self.repositories = repositories
        self.legacy_champion = {"strategy_id": "legacy_champion", "strategy_type": "legacy", "role": "champion", "status": "active"}

    def list_strategies(self) -> list[dict[str, Any]]:
        if self.registry is None:
            return [dict(self.legacy_champion)]
        if hasattr(self.registry, "list_portfolio_strategies"):
            return self.registry.list_portfolio_strategies()
        return self.registry.list_strategies()

    def select_strategy(self, task_name: str | None = None) -> dict[str, Any]:
        if not getattr(self.config, "enable_strategy_portfolio", True):
            return self._champion(task_name)
        if not getattr(self.config, "enable_challenger_live_budget", False):
            return self._champion(task_name)
        strategies = self._with_safety(self.list_strategies())
        allocations = self.budget_allocator.allocate(strategies) if self.budget_allocator else {"legacy_champion": 1.0}
        roll = random.random()
        acc = 0.0
        by_id = {str(s.get("strategy_id")): s for s in strategies}
        for sid, budget in allocations.items():
            acc += float(budget or 0.0)
            if roll <= acc:
                selected = by_id.get(sid, self._champion(task_name))
                if selected.get("role") == "challenger" and not bool(selected.get("safety_pass")):
                    return self._champion(task_name)
                return dict(selected)
        return self._champion(task_name)

    def record_strategy_decision(self, strategy: dict, workflow_context: dict, selected: bool, shadow: bool, score: float | None = None) -> None:
        repo = getattr(self.repositories, "strategy", None) if self.repositories is not None else None
        if repo is None:
            return
        context = workflow_context if isinstance(workflow_context, dict) else {}
        strategy = strategy if isinstance(strategy, dict) else {}
        repo.insert_strategy_decision({
            "strategy_id": strategy.get("strategy_id", "legacy_champion"),
            "alpha_id": context.get("alpha_id", ""),
            "decision_type": context.get("decision_type", "strategy_selection"),
            "selected": bool(selected),
            "shadow": bool(shadow),
            "score": score,
            "model_version": strategy.get("model_version", ""),
            "raw_payload": {"strategy": strategy, "workflow_context": context},
        })

    def record_result(self, *args: Any, **kwargs: Any) -> None:
        return None

    def maybe_promote(self) -> dict[str, Any]:
        if not getattr(self.config, "enable_auto_promotion", False):
            return {"promoted": False, "reason": "auto_promotion_disabled"}
        if self.promotion_policy is None:
            return {"promoted": False, "reason": "promotion_policy_unavailable"}
        results = []
        for challenger in self.registry.list_challengers() if self.registry else []:
            results.append(self.promotion_policy.promote_if_eligible(str(challenger.get("strategy_id"))))
        return {"promoted": any(bool(r.get("promoted")) for r in results), "results": results}

    def maybe_rollback(self) -> dict[str, Any]:
        if not getattr(self.config, "enable_auto_rollback", False):
            return {"rolled_back": False, "reason": "auto_rollback_disabled"}
        if self.rollback_policy is None:
            return {"rolled_back": False, "reason": "rollback_policy_unavailable"}
        evaluation = self.rollback_policy.evaluate_rollback()
        if evaluation.get("rollback_pass"):
            return self.rollback_policy.rollback_to_previous_champion(str(evaluation.get("reason") or "auto_rollback"))
        return evaluation

    def rollback(self) -> dict[str, Any]:
        if self.rollback_policy is None:
            return {"rolled_back": False, "reason": "rollback_policy_unavailable"}
        return self.rollback_policy.rollback_to_legacy("manual_portfolio_rollback")

    def _champion(self, task_name: str | None = None) -> dict[str, Any]:
        if self.registry is None:
            return dict(self.legacy_champion)
        return dict(self.registry.get_champion(task_name))

    def _with_safety(self, strategies: list[dict[str, Any]]) -> list[dict[str, Any]]:
        replay_repo = getattr(self.repositories, "replay", None) if self.repositories is not None else None
        out = []
        for strategy in strategies:
            item = dict(strategy)
            if item.get("role") == "challenger" and replay_repo is not None:
                report = replay_repo.latest_model_safety_report(strategy_id=str(item.get("strategy_id") or ""))
                item["safety_pass"] = bool((report or {}).get("safety_pass"))
                item["safety_status"] = (report or {}).get("safety_status", "unknown")
            out.append(item)
        return out
