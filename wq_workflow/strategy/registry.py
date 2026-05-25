from __future__ import annotations

from typing import Any

from .schema import StrategyProfile, utc_now_iso

DEFAULT_STRATEGIES: tuple[dict[str, Any], ...] = (
    {"strategy_id": "legacy_champion", "strategy_type": "legacy", "role": "champion", "task_name": "", "status": "active"},
    {"strategy_id": "parent_learning_challenger", "strategy_type": "learned_parent", "role": "challenger", "task_name": "parent", "status": "active"},
    {"strategy_id": "policy_learning_challenger", "strategy_type": "learned_policy", "role": "challenger", "task_name": "policy", "status": "active"},
    {"strategy_id": "simulator_learning_challenger", "strategy_type": "learned_simulator", "role": "challenger", "task_name": "simulator", "status": "active"},
    {"strategy_id": "sc_learning_challenger", "strategy_type": "learned_sc", "role": "challenger", "task_name": "sc", "status": "active"},
    {"strategy_id": "random_baseline", "strategy_type": "baseline", "role": "baseline", "task_name": "", "status": "active"},
)

DEFAULT_STRATEGY_PROFILES: tuple[dict[str, Any], ...] = (
    {"strategy_id": "legacy_baseline", "strategy_type": "legacy_baseline", "name": "Legacy baseline", "description": "Production safety baseline from the legacy main workflow.", "source": "legacy"},
    {"strategy_id": "random_exploration", "strategy_type": "random_exploration", "name": "Random exploration", "description": "Exploratory candidate strategy used to preserve exploration budget.", "source": "manual"},
    {"strategy_id": "experiment_budget", "strategy_type": "experiment_budget", "name": "Experiment budget advisory", "description": "Advisory strategy derived from experiment planning and budget evidence.", "source": "experiment"},
    {"strategy_id": "ml_parent_policy", "strategy_type": "ml_parent_policy", "name": "ML parent policy", "description": "Parent selection advisory strategy from ML parent learning.", "source": "ml"},
    {"strategy_id": "ml_mutation_policy", "strategy_type": "ml_mutation_policy", "name": "ML mutation policy", "description": "Mutation/action advisory strategy from ML policy learning.", "source": "ml"},
    {"strategy_id": "replay_supported_policy", "strategy_type": "replay_supported_policy", "name": "Replay-supported policy", "description": "Policy family supported by offline replay metrics and comparisons.", "source": "replay"},
    {"strategy_id": "counterfactual_supported_policy", "strategy_type": "counterfactual_supported_policy", "name": "Counterfactual-supported policy", "description": "Policy family supported by conservative counterfactual estimates.", "source": "counterfactual"},
    {"strategy_id": "governance_safe_policy", "strategy_type": "governance_safe_policy", "name": "Governance-safe policy", "description": "Policy family recorded from Governance allow/block evidence.", "source": "governance"},
    {"strategy_id": "manual_or_unknown", "strategy_type": "manual_or_unknown", "name": "Manual or unknown", "description": "Fallback profile for unknown or manual strategy sources.", "source": "unknown"},
)


class StrategyRegistry:
    """Compatibility registry plus the Phase 6A advisory StrategyProfile registry."""

    def __init__(self, repositories: Any | None = None, config: Any | None = None, logger: Any | None = None, profile_repository: Any | None = None) -> None:
        self.repositories = repositories
        self.config = config
        self.logger = logger
        self.profile_repository = profile_repository
        self._profiles: dict[str, StrategyProfile] = {profile.strategy_id: profile for profile in self.default_profiles()}

    @property
    def repo(self) -> Any:
        return getattr(self.repositories, "strategy", None)

    def default_profiles(self) -> list[StrategyProfile]:
        now = utc_now_iso()
        profiles: list[StrategyProfile] = []
        for item in DEFAULT_STRATEGY_PROFILES:
            payload = {"enabled": True, "advisory_only": True, "created_at": now, "updated_at": now, "raw_payload": {"created_by": "phase6a_default_strategy"}, **item}
            profiles.append(StrategyProfile.from_dict(payload))
        return profiles

    def ensure_default_strategies(self) -> None:
        for profile in self.default_profiles():
            self.register_strategy(profile)
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

    def register_strategy(self, profile: StrategyProfile | dict[str, Any]) -> str:
        data = profile.to_dict() if isinstance(profile, StrategyProfile) else dict(profile or {})
        if "role" in data or data.get("status") or data.get("task_name"):
            if self.repo is None:
                return str(data.get("strategy_id") or "")
            payload = dict(data)
            payload.setdefault("status", "active")
            payload.setdefault("role", "challenger")
            try:
                return self.repo.upsert_strategy(payload)
            except Exception:
                return str(payload.get("strategy_id") or "")
        strategy_profile = StrategyProfile.from_dict(data)
        if not strategy_profile.strategy_id:
            return ""
        self._profiles[strategy_profile.strategy_id] = strategy_profile
        if self.profile_repository is not None:
            try:
                self.profile_repository.save_profile(strategy_profile)
            except Exception as exc:
                self._warn("strategy profile save skipped: %s", exc)
        return strategy_profile.strategy_id

    def get_strategy(self, strategy_id: str) -> StrategyProfile | None:
        sid = str(strategy_id or "")
        if not sid:
            return None
        if self.profile_repository is not None:
            try:
                profile = self.profile_repository.get_profile(sid)
                if profile is not None:
                    return profile
            except Exception as exc:
                self._warn("strategy profile read skipped: %s", exc)
        return self._profiles.get(sid)

    def list_strategies(self, strategy_type: str | None = None) -> list[StrategyProfile]:
        if self.profile_repository is not None:
            try:
                rows = self.profile_repository.list_profiles(strategy_type=strategy_type)
                if rows:
                    return rows
            except Exception as exc:
                self._warn("strategy profile list skipped: %s", exc)
        rows = list(self._profiles.values())
        if strategy_type:
            rows = [profile for profile in rows if profile.strategy_type == strategy_type]
        return sorted(rows, key=lambda item: item.strategy_id)

    def list_profiles(self, strategy_type: str | None = None) -> list[StrategyProfile]:
        return self.list_strategies(strategy_type=strategy_type)

    def list_portfolio_strategies(self, status: str | None = None) -> list[dict[str, Any]]:
        self.ensure_default_strategies()
        if self.repo is None:
            return [dict(item) for item in DEFAULT_STRATEGIES if status is None or item.get("status") == status]
        try:
            return self.repo.list_strategies(status=status)
        except Exception:
            return [dict(item) for item in DEFAULT_STRATEGIES if status is None or item.get("status") == status]

    def get_champion(self, task_name: str | None = None) -> dict[str, Any]:
        self.ensure_default_strategies()
        try:
            rows = self.repo.list_by_role("champion", task_name=task_name) if self.repo is not None else []
        except Exception:
            rows = []
        return rows[0] if rows else {"strategy_id": getattr(self.config, "strategy_default_champion", "legacy_champion"), "strategy_type": "legacy", "role": "champion", "status": "active"}

    def list_challengers(self, task_name: str | None = None) -> list[dict[str, Any]]:
        self.ensure_default_strategies()
        try:
            rows = self.repo.list_by_role("challenger", task_name=task_name) if self.repo is not None else []
        except Exception:
            rows = [dict(item) for item in DEFAULT_STRATEGIES if item.get("role") == "challenger" and (not task_name or item.get("task_name") in {task_name, ""})]
        return rows

    def update_role(self, strategy_id: str, role: str, reason: str) -> None:
        if self.repo is not None:
            try:
                self.repo.update_role(strategy_id, role, reason)
            except Exception:
                pass

    def deactivate_strategy(self, strategy_id: str, reason: str) -> None:
        if self.repo is not None:
            try:
                self.repo.deactivate_strategy(strategy_id, reason)
            except Exception:
                pass

    def _warn(self, message: str, exc: Exception) -> None:
        try:
            if self.logger is not None:
                self.logger.warning(message, exc)
        except Exception:
            pass
