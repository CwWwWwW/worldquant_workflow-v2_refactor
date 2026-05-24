from __future__ import annotations

from typing import Any

from wq_workflow.data.json_utils import safe_float, safe_int
from wq_workflow.offline.report import load_latest_replay_report, save_model_safety_report


class PromotionPolicy:
    def __init__(self, repositories: Any, offline_replay: Any, support_checker: Any, config: Any, logger: Any | None = None) -> None:
        self.repositories = repositories
        self.offline_replay = offline_replay
        self.support_checker = support_checker
        self.config = config
        self.logger = logger

    def evaluate_promotion(self, strategy_id: str) -> dict:
        strategy_repo = getattr(self.repositories, "strategy", None)
        strategy = strategy_repo.get_strategy(strategy_id) if strategy_repo is not None else None
        reasons: list[str] = []
        metrics: dict[str, Any] = {}
        if not strategy:
            reasons.append("strategy_not_found")
            return self._result(False, strategy_id, reasons, metrics)
        if strategy.get("status", "active") != "active":
            reasons.append("strategy_not_active")
        if strategy.get("role") != "challenger":
            reasons.append("strategy_not_challenger")
        task = str(strategy.get("task_name") or self._task_from_strategy(strategy_id))
        model_version = str(strategy.get("model_version") or "")

        replay = load_latest_replay_report(self.repositories, task_name=task or None, strategy_id=strategy_id) or {}
        if not replay and self.offline_replay is not None and task:
            replay = self.offline_replay.evaluate_task(task, model_version=model_version or None)
        metrics.update(replay if isinstance(replay, dict) else {})
        support = self.support_checker.check_strategy_support(strategy_id) if self.support_checker is not None else {"support_pass": False, "support_coverage": 0.0}
        metrics["support"] = support
        validation_pass = self._validation_pass(task, model_version)
        metrics["validation_pass"] = validation_pass

        if getattr(self.config, "promotion_require_model_validation_pass", True) and not validation_pass:
            reasons.append("validation_fail")
        if getattr(self.config, "promotion_require_offline_replay_pass", True) and not bool(replay.get("replay_pass")):
            reasons.append("offline_replay_fail")
        if not bool(support.get("support_pass")):
            reasons.append("support_insufficient")
        if safe_int(replay.get("sample_count"), 0) < int(getattr(self.config, "promotion_min_samples", 200) or 200):
            reasons.append("sample_count_below_minimum")
        if safe_float(replay.get("support_coverage"), 0.0) < float(getattr(self.config, "promotion_min_support_coverage", 0.65) or 0.65):
            reasons.append("support_coverage_below_minimum")
        if safe_float(replay.get("estimated_reward_delta"), 0.0) < float(getattr(self.config, "promotion_min_reward_improvement", 0.05) or 0.05):
            reasons.append("reward_improvement_below_minimum")
        if safe_float(replay.get("estimated_sc_risk_delta", replay.get("estimated_risk_delta")), 0.0) > float(getattr(self.config, "promotion_max_sc_risk_delta", 0.03) or 0.03):
            reasons.append("sc_risk_delta_above_maximum")
        if safe_float(replay.get("estimated_failure_delta"), 0.0) > float(getattr(self.config, "promotion_max_failure_rate_delta", 0.03) or 0.03):
            reasons.append("failure_delta_above_maximum")
        if self._has_severe_drift():
            reasons.append("severe_drift")

        return self._result(not reasons, strategy_id, list(dict.fromkeys(reasons)), metrics)

    def promote_if_eligible(self, strategy_id: str) -> dict:
        evaluation = self.evaluate_promotion(strategy_id)
        if not evaluation.get("promotion_pass"):
            self._write_safety(strategy_id, evaluation, promoted=False)
            return {"promoted": False, **evaluation}
        strategy_repo = getattr(self.repositories, "strategy", None)
        if strategy_repo is None:
            return {"promoted": False, **evaluation, "reasons": [*evaluation.get("reasons", []), "strategy_repository_unavailable"]}
        current = strategy_repo.list_by_role("champion")
        for champion in current:
            strategy_repo.update_role(str(champion.get("strategy_id")), "previous_champion", f"promoted {strategy_id}")
        strategy_repo.update_role(strategy_id, "champion", "promotion_policy_passed")
        strategy_repo.insert_allocation({"strategy_id": strategy_id, "role": "champion", "budget": 1.0, "reason": "promotion_policy_passed"})
        self._write_safety(strategy_id, evaluation, promoted=True)
        return {"promoted": True, **evaluation}

    def _validation_pass(self, task: str, model_version: str) -> bool:
        if not task:
            return False
        registry = getattr(self.offline_replay, "model_registry", None)
        meta = None
        try:
            if model_version and registry is not None:
                meta = registry.get_model_metadata(task, model_version)
        except Exception:
            meta = None
        try:
            if not meta and registry is not None:
                active = registry.load_active_model(task)
                meta = (active or {}).get("payload")
        except Exception:
            meta = None
        if not meta:
            return False
        return bool(meta.get("validation_passed") or (meta.get("validation_gate") or {}).get("passed"))

    def _has_severe_drift(self) -> bool:
        drift = getattr(self.repositories, "drift", None)
        if drift is None:
            return False
        try:
            return any(str(e.get("severity", "")).lower() == "severe" for e in drift.list_recent_events(limit=20))
        except Exception:
            return False

    def _task_from_strategy(self, strategy_id: str) -> str:
        for name in ("parent", "policy", "simulator", "sc"):
            if strategy_id.startswith(name):
                return name
        return ""

    def _result(self, passed: bool, strategy_id: str, reasons: list[str], metrics: dict[str, Any]) -> dict:
        return {"promotion_pass": bool(passed), "strategy_id": strategy_id, "reasons": reasons, "metrics": metrics}

    def _write_safety(self, strategy_id: str, evaluation: dict, promoted: bool) -> None:
        metrics = evaluation.get("metrics") if isinstance(evaluation.get("metrics"), dict) else {}
        save_model_safety_report(self.repositories, {
            "strategy_id": strategy_id,
            "task_name": (metrics or {}).get("task_name", ""),
            "model_version": (metrics or {}).get("model_version", ""),
            "validation_pass": bool(metrics.get("validation_pass")),
            "replay_pass": bool(metrics.get("replay_pass")),
            "support_pass": bool((metrics.get("support") or {}).get("support_pass")) if isinstance(metrics.get("support"), dict) else False,
            "promotion_pass": bool(evaluation.get("promotion_pass")),
            "safety_status": "pass" if promoted else "fail",
            "reasons": evaluation.get("reasons", []),
            "raw_payload": {"evaluation": evaluation},
        })
