from __future__ import annotations

from typing import Any

from wq_workflow.offline.report import load_latest_replay_report, save_model_safety_report


class ModelSafetyGate:
    def __init__(self, repositories: Any, config: Any, logger: Any | None = None, model_registry: Any | None = None, support_checker: Any | None = None) -> None:
        self.repositories = repositories
        self.config = config
        self.logger = logger
        self.model_registry = model_registry
        self.support_checker = support_checker

    def evaluate(self, task_name: str, model_version: str, strategy_id: str) -> dict:
        reasons: list[str] = []
        active = self._model_active(task_name, model_version)
        validation = self._validation_pass(task_name, model_version)
        replay = load_latest_replay_report(self.repositories, task_name=task_name, strategy_id=strategy_id) or {}
        support = self.support_checker.check_strategy_support(strategy_id) if self.support_checker is not None else {"support_pass": False}
        if not validation:
            reasons.append("validation_fail")
        if not replay.get("replay_pass"):
            reasons.append("replay_fail")
        if not support.get("support_pass"):
            reasons.append("support_fail")
        if not active:
            reasons.append("model_not_active")
        if self._has_severe_drift():
            reasons.append("severe_drift")
        if self.model_registry is None:
            reasons.append("missing_model_registry")
        safety_pass = not reasons
        report = {
            "task_name": task_name,
            "model_version": model_version,
            "strategy_id": strategy_id,
            "validation_pass": validation,
            "replay_pass": bool(replay.get("replay_pass")),
            "support_pass": bool(support.get("support_pass")),
            "promotion_pass": safety_pass,
            "safety_pass": safety_pass,
            "safety_status": "pass" if safety_pass else "fail",
            "reasons": reasons,
            "metrics": {"replay": replay, "support": support, "model_active": active},
        }
        report["report_id"] = save_model_safety_report(self.repositories, report) or report.get("report_id", "")
        return report

    def _validation_pass(self, task_name: str, model_version: str) -> bool:
        try:
            meta = self.model_registry.get_model_metadata(task_name, model_version) if self.model_registry and model_version else None
            if not meta and self.model_registry:
                active = self.model_registry.load_active_model(task_name)
                meta = (active or {}).get("payload")
            return bool((meta or {}).get("validation_passed") or ((meta or {}).get("validation_gate") or {}).get("passed"))
        except Exception:
            return False

    def _model_active(self, task_name: str, model_version: str) -> bool:
        try:
            active = self.model_registry.load_active_model(task_name) if self.model_registry else None
            if not active:
                return False
            return not model_version or str(active.get("model_version") or "") == str(model_version)
        except Exception:
            return False

    def _has_severe_drift(self) -> bool:
        drift = getattr(self.repositories, "drift", None)
        if drift is None:
            return False
        try:
            return any(str(e.get("severity", "")).lower() == "severe" for e in drift.list_recent_events(limit=20))
        except Exception:
            return False
