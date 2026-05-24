from __future__ import annotations

from typing import Any

from wq_workflow.data.json_utils import safe_float
from wq_workflow.offline.report import save_model_safety_report


class RollbackPolicy:
    def __init__(self, repositories: Any, performance_tracker: Any, config: Any, logger: Any | None = None) -> None:
        self.repositories = repositories
        self.performance_tracker = performance_tracker
        self.config = config
        self.logger = logger

    def evaluate_rollback(self, strategy_id: str | None = None) -> dict:
        repo = getattr(self.repositories, "strategy", None)
        if repo is None:
            return {"rollback_pass": False, "reason": "strategy_repository_unavailable", "reasons": ["strategy_repository_unavailable"]}
        strategy = repo.get_strategy(strategy_id) if strategy_id else (repo.list_by_role("champion")[0] if repo.list_by_role("champion") else None)
        sid = str((strategy or {}).get("strategy_id") or "legacy_champion")
        if sid == "legacy_champion":
            return {"rollback_pass": False, "strategy_id": sid, "reason": "legacy_champion_active", "reasons": []}
        comparison = self.performance_tracker.compare_champion_vs_challenger("legacy_champion", sid) if self.performance_tracker else {}
        reasons: list[str] = []
        if -safe_float(comparison.get("reward_delta"), 0.0) >= float(getattr(self.config, "rollback_reward_drop_threshold", 0.10) or 0.10):
            reasons.append("recent_reward_drop")
        if safe_float(comparison.get("sc_risk_delta"), 0.0) >= float(getattr(self.config, "rollback_sc_risk_increase_threshold", 0.05) or 0.05):
            reasons.append("sc_risk_increase")
        if safe_float(comparison.get("failure_rate_delta"), 0.0) >= float(getattr(self.config, "rollback_failure_rate_increase_threshold", 0.05) or 0.05):
            reasons.append("failure_rate_increase")
        safety = getattr(self.repositories, "replay", None)
        latest = safety.latest_model_safety_report(strategy_id=sid) if safety is not None else None
        if latest and latest.get("safety_status") in {"invalid", "fail"}:
            reasons.append("safety_report_invalidated")
        return {"rollback_pass": bool(reasons), "strategy_id": sid, "reason": ",".join(reasons), "reasons": reasons, "metrics": comparison}

    def rollback_to_legacy(self, reason: str) -> dict:
        return self._rollback("legacy_champion", reason or "manual_rollback_to_legacy")

    def rollback_to_previous_champion(self, reason: str) -> dict:
        repo = getattr(self.repositories, "strategy", None)
        previous = repo.list_by_role("previous_champion")[0] if repo is not None and repo.list_by_role("previous_champion") else None
        target = str((previous or {}).get("strategy_id") or "legacy_champion")
        return self._rollback(target, reason or "manual_rollback_to_previous_champion")

    def _rollback(self, target_id: str, reason: str) -> dict:
        repo = getattr(self.repositories, "strategy", None)
        if repo is None:
            return {"rolled_back": False, "reason": "strategy_repository_unavailable"}
        for champion in repo.list_by_role("champion"):
            if str(champion.get("strategy_id")) != target_id:
                repo.update_role(str(champion.get("strategy_id")), "challenger", f"rollback:{reason}")
        repo.update_role(target_id, "champion", f"rollback:{reason}")
        repo.insert_allocation({"strategy_id": target_id, "role": "champion", "budget": 1.0, "reason": f"rollback:{reason}"})
        save_model_safety_report(self.repositories, {
            "strategy_id": target_id,
            "validation_pass": True,
            "replay_pass": True,
            "support_pass": True,
            "promotion_pass": True,
            "safety_status": "pass",
            "reason": f"rollback_target:{reason}",
            "raw_payload": {"rollback_reason": reason},
        })
        return {"rolled_back": True, "target_strategy_id": target_id, "reason": reason, "deleted_model": False}
