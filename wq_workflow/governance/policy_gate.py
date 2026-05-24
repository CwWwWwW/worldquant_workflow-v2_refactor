from __future__ import annotations

from typing import Any

from .lifecycle import is_expired, is_hard_decision_allowed_status
from .schema import GovernanceDecision

FLAG_BY_TASK = {
    "sc": "enable_sc_model_fallback",
    "parent": "enable_parent_model_decision",
    "policy": "enable_policy_model_decision",
    "simulator": "enable_simulator_model_skip",
    "outcome": "enable_simulator_model_skip",
}


class GovernancePolicyGate:
    def __init__(self, registry_adapter: Any | None = None, config: Any | None = None, event_logger: Any | None = None, status_reader: Any | None = None, logger: Any | None = None, available: bool = True) -> None:
        self.registry_adapter = registry_adapter
        self.config = config
        self.event_logger = event_logger
        self.status_reader = status_reader
        self.logger = logger
        self.available = available

    def _event(self, decision: GovernanceDecision, event_type: str) -> None:
        try:
            if self.event_logger is not None:
                self.event_logger.record(task_name=decision.task_name, model_version=decision.model_version, event_type=event_type, severity="warning" if not decision.allowed else "info", message=decision.reason, action_taken="allow_hard_decision" if decision.allowed else "disable_hard_decision", raw_payload=decision.to_dict())
        except Exception:
            pass

    def allow_hard_decision(self, task_name: str, decision_type: str, effective_config: Any | None = None) -> GovernanceDecision:
        task = str(task_name or "")
        cfg = effective_config or self.config
        warnings: list[str] = []
        if not self.available or self.registry_adapter is None:
            d = GovernanceDecision(False, "governance_unavailable", task, str(decision_type or ""), fallback_required=True, warnings=["governance unavailable"])
            self._event(d, "hard_decision_disabled")
            return d
        flag = FLAG_BY_TASK.get(task, f"enable_{task}_model_decision")
        flag_enabled = bool(getattr(cfg, flag, False)) if cfg is not None else False
        force_unsafe = bool(getattr(cfg, "force_enable_unsafe_ml_decisions", False)) if cfg is not None else False
        if not flag_enabled:
            return GovernanceDecision(False, f"{flag}_disabled", task, str(decision_type or ""), fallback_required=True)
        meta = self.registry_adapter.get_active_metadata(task)
        consistency = self.registry_adapter.check_registry_consistency(task)
        if force_unsafe:
            warnings.append("UNSAFE force_enable_unsafe_ml_decisions=true; governance checks bypassed")
            d = GovernanceDecision(True, "force_unsafe_allowed", task, str(decision_type or ""), (meta or {}).get("model_version"), (meta or {}).get("lifecycle_status"), float((meta or {}).get("model_weight", 0.0) or 0.0), False, warnings, {"consistency": consistency})
            self._event(d, "hard_decision_allowed")
            return d
        if not meta:
            d = GovernanceDecision(False, "no_active_model", task, str(decision_type or ""), fallback_required=True, raw_payload={"flag": flag})
            self._event(d, "hard_decision_disabled")
            return d
        raw = meta.get("raw_payload") if isinstance(meta.get("raw_payload"), dict) else {}
        status = str(raw.get("lifecycle_status") or meta.get("lifecycle_status") or "shadow")
        version = str(meta.get("model_version") or "")
        weight = float(raw.get("model_weight", meta.get("model_weight", 0.0)) or 0.0)
        if not consistency.get("ok", False):
            d = GovernanceDecision(False, "registry_inconsistent", task, str(decision_type or ""), version, status, weight, True, raw_payload={"consistency": consistency})
            self._event(d, "hard_decision_disabled")
            return d
        if not is_hard_decision_allowed_status(status):
            d = GovernanceDecision(False, f"lifecycle_status_not_allowed:{status}", task, str(decision_type or ""), version, status, weight, True)
            self._event(d, "hard_decision_disabled")
            return d
        expires_at = raw.get("expires_at") or meta.get("expires_at")
        if expires_at and is_expired(expires_at):
            d = GovernanceDecision(False, "model_expired", task, str(decision_type or ""), version, status, weight, True)
            self._event(d, "hard_decision_disabled")
            return d
        online = raw.get("last_online_eval") if isinstance(raw.get("last_online_eval"), dict) else {}
        recommended = str(online.get("recommended_action") or "")
        if recommended in {"reduce_weight", "disable_model", "rollback", "force_legacy"}:
            d = GovernanceDecision(False, f"online_evaluation_blocks:{recommended}", task, str(decision_type or ""), version, status, weight, True, raw_payload={"online_eval": online})
            self._event(d, "hard_decision_disabled")
            return d
        if task == "parent":
            if float(getattr(cfg, "min_legacy_baseline_budget", 0.10) or 0.10) <= 0:
                return GovernanceDecision(False, "legacy_baseline_budget_missing", task, str(decision_type or ""), version, status, weight, True)
        if task == "policy":
            if not bool(raw.get("has_decision_snapshot_history", True)):
                return GovernanceDecision(False, "no_decision_snapshot_history", task, str(decision_type or ""), version, status, weight, True)
        if task in {"simulator", "outcome"}:
            false_rate = raw.get("false_skip_rate")
            max_rate = float(getattr(cfg, "simulator_max_false_skip_rate", 0.02) or 0.02)
            budget = float(getattr(cfg, "simulator_validation_backtest_budget", 0.10) or 0.0)
            if false_rate is None:
                return GovernanceDecision(False, "simulator_false_skip_risk_unknown", task, str(decision_type or ""), version, status, weight, True)
            try:
                if float(false_rate) > max_rate:
                    return GovernanceDecision(False, "simulator_false_skip_risk_too_high", task, str(decision_type or ""), version, status, weight, True)
            except Exception:
                return GovernanceDecision(False, "simulator_false_skip_risk_invalid", task, str(decision_type or ""), version, status, weight, True)
            if budget <= 0:
                return GovernanceDecision(False, "simulator_validation_budget_missing", task, str(decision_type or ""), version, status, weight, True)
        d = GovernanceDecision(True, "hard_decision_allowed", task, str(decision_type or ""), version, status, weight, False, warnings)
        self._event(d, "hard_decision_allowed")
        return d
