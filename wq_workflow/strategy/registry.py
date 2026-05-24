from __future__ import annotations

from typing import Any


DEFAULT_STRATEGIES: tuple[dict[str, Any], ...] = (
    {"strategy_id": "legacy_champion", "strategy_type": "legacy", "role": "champion", "task_name": "", "status": "active"},
    {"strategy_id": "parent_learning_challenger", "strategy_type": "learned_parent", "role": "challenger", "task_name": "parent", "status": "active"},
    {"strategy_id": "policy_learning_challenger", "strategy_type": "learned_policy", "role": "challenger", "task_name": "policy", "status": "active"},
    {"strategy_id": "simulator_learning_challenger", "strategy_type": "learned_simulator", "role": "challenger", "task_name": "simulator", "status": "active"},
    {"strategy_id": "sc_learning_challenger", "strategy_type": "learned_sc", "role": "challenger", "task_name": "sc", "status": "active"},
    {"strategy_id": "random_baseline", "strategy_type": "baseline", "role": "baseline", "task_name": "", "status": "active"},
)


class StrategyRegistry:
    def __init__(self, repositories: Any, config: Any, logger: Any | None = None) -> None:
        self.repositories = repositories
        self.config = config
        self.logger = logger

    @property
    def repo(self) -> Any:
        return getattr(self.repositories, "strategy", None)

    def ensure_default_strategies(self) -> None:
        if self.repo is None:
            return
        for item in DEFAULT_STRATEGIES:
            try:
                existing = self.repo.get_strategy(item["strategy_id"])
            except Exception:
                return
            if existing:
                continue
            payload = dict(item)
            payload.setdefault("raw_payload", {"created_by": "stage5_default_strategy"})
            try:
                self.repo.upsert_strategy(payload)
            except Exception:
                return

    def register_strategy(self, strategy: dict) -> str:
        if self.repo is None:
            return str((strategy or {}).get("strategy_id") or "")
        data = dict(strategy or {})
        data.setdefault("status", "active")
        data.setdefault("role", "challenger")
        try:
            return self.repo.upsert_strategy(data)
        except Exception:
            return str(data.get("strategy_id") or "")

    def list_strategies(self, status: str | None = None) -> list[dict]:
        self.ensure_default_strategies()
        if self.repo is None:
            return [dict(item) for item in DEFAULT_STRATEGIES]
        try:
            return self.repo.list_strategies(status=status)
        except Exception:
            return [dict(item) for item in DEFAULT_STRATEGIES if status is None or item.get("status") == status]

    def get_champion(self, task_name: str | None = None) -> dict:
        self.ensure_default_strategies()
        try:
            rows = self.repo.list_by_role("champion", task_name=task_name) if self.repo is not None else []
        except Exception:
            rows = []
        return rows[0] if rows else {"strategy_id": getattr(self.config, "strategy_default_champion", "legacy_champion"), "strategy_type": "legacy", "role": "champion", "status": "active"}

    def list_challengers(self, task_name: str | None = None) -> list[dict]:
        self.ensure_default_strategies()
        try:
            rows = self.repo.list_by_role("challenger", task_name=task_name) if self.repo is not None else []
        except Exception:
            rows = [dict(item) for item in DEFAULT_STRATEGIES if item.get("role") == "challenger" and (not task_name or item.get("task_name") in {task_name, ""})]
        return rows

    def update_role(self, strategy_id: str, role: str, reason: str) -> None:
        if self.repo is not None:
            self.repo.update_role(strategy_id, role, reason)

    def deactivate_strategy(self, strategy_id: str, reason: str) -> None:
        if self.repo is not None:
            self.repo.deactivate_strategy(strategy_id, reason)
