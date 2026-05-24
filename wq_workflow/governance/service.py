from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from .events import ModelEventLogger
from .long_term_guard import LongTermGuard
from .online_evaluation import OnlineEvaluator
from .policy_gate import FLAG_BY_TASK, GovernancePolicyGate
from .registry_adapter import RegistryAdapter
from .retrain_scheduler import RetrainScheduler
from .sample_quality import SampleQualityChecker
from .schema import GovernanceCheckResult, GovernanceDecision
from .status_writer import StatusWriter


class LearningGovernanceService:
    def __init__(self, *, config: Any | None = None, model_registry: Any | None = None, storage: Any | None = None, db_conn: sqlite3.Connection | None = None, db_path: str | Path | None = None, model_root: str | Path | None = None, logger: Any | None = None, trainers: dict[str, Any] | None = None, root: str | Path | None = None) -> None:
        self.config = config
        self.logger = logger
        self.available = True
        try:
            if db_path is None:
                db_path = getattr(getattr(storage, "config", None), "db_path", None) or getattr(config, "storage_db_path", None)
            self.event_logger = ModelEventLogger(conn=db_conn, db_path=db_path, logger=logger)
            self.registry_adapter = RegistryAdapter(model_registry=model_registry, db_conn=db_conn, db_path=db_path, model_root=model_root, logger=logger, root=root)
            self.online_evaluator = OnlineEvaluator(conn=db_conn, db_path=db_path, config=config, logger=logger)
            self.sample_quality_checker = SampleQualityChecker(config=config, event_logger=self.event_logger, logger=logger)
            status_path = getattr(config, "governance_status_path", "runtime/status/governance_status.json") if config is not None else "runtime/status/governance_status.json"
            ml_status_path = getattr(config, "ml_status_path", "runtime/status/ml_status.json") if config is not None else "runtime/status/ml_status.json"
            self.status_writer = StatusWriter(status_path=status_path, ml_status_path=ml_status_path, logger=logger, root=root)
            self.retrain_scheduler = RetrainScheduler(config=config, registry_adapter=self.registry_adapter, sample_quality_checker=self.sample_quality_checker, event_logger=self.event_logger, trainers=trainers, logger=logger)
            self.long_term_guard = LongTermGuard(registry_adapter=self.registry_adapter, online_evaluator=self.online_evaluator, retrain_scheduler=self.retrain_scheduler, status_writer=self.status_writer, event_logger=self.event_logger, config=config, logger=logger)
            self.policy_gate = GovernancePolicyGate(registry_adapter=self.registry_adapter, config=config, event_logger=self.event_logger, logger=logger, available=True)
        except Exception as exc:
            self.available = False
            self.init_error = exc
            self.event_logger = None
            self.registry_adapter = None
            self.online_evaluator = None
            self.sample_quality_checker = None
            self.status_writer = None
            self.retrain_scheduler = None
            self.long_term_guard = None
            self.policy_gate = GovernancePolicyGate(available=False, config=config, logger=logger)
            try:
                if logger is not None:
                    logger.warning("learning governance init failed: %s", exc)
            except Exception:
                pass

    def check_task(self, task_name: str) -> GovernanceCheckResult:
        try:
            if not self.available or self.long_term_guard is None:
                return GovernanceCheckResult(ok=False, task_name=str(task_name or ""), recommended_action="force_legacy", reason="governance_unavailable")
            return self.long_term_guard.check_task(task_name)
        except Exception as exc:
            self.record_model_event(task_name=task_name, event_type="governance_check_failed", severity="warning", message=str(exc), action_taken="force_legacy")
            return GovernanceCheckResult(ok=False, task_name=str(task_name or ""), recommended_action="force_legacy", reason=f"check_exception:{exc}")

    def check_all_tasks(self) -> dict[str, GovernanceCheckResult]:
        try:
            if not self.available or self.long_term_guard is None:
                return {}
            return self.long_term_guard.check_all_tasks()
        except Exception as exc:
            self.record_model_event(event_type="governance_check_failed", severity="warning", message=str(exc), action_taken="force_legacy")
            return {}

    def allow_hard_decision(self, task_name: str, decision_type: str, effective_config: Any | None = None) -> GovernanceDecision:
        try:
            if not self.available or self.policy_gate is None:
                return GovernanceDecision(False, "governance_unavailable", str(task_name or ""), str(decision_type or ""), fallback_required=True)
            return self.policy_gate.allow_hard_decision(task_name, decision_type, effective_config or self.config)
        except Exception as exc:
            self.record_model_event(task_name=task_name, event_type="hard_decision_disabled", severity="warning", message=str(exc), action_taken="force_legacy")
            return GovernanceDecision(False, f"gate_exception:{exc}", str(task_name or ""), str(decision_type or ""), fallback_required=True)

    def handle_prediction_error(self, task_name: str, error: Exception | str) -> GovernanceCheckResult:
        self.record_model_event(task_name=task_name, event_type="model_prediction_error", severity="warning", message=str(error), action_taken="force_legacy")
        return GovernanceCheckResult(ok=False, task_name=str(task_name or ""), recommended_action="force_legacy", reason="prediction_error")

    def handle_model_load_error(self, task_name: str, error: Exception | str) -> GovernanceCheckResult:
        self.record_model_event(task_name=task_name, event_type="model_load_error", severity="warning", message=str(error), action_taken="disable_hard_decision")
        try:
            if self.registry_adapter is not None:
                self.registry_adapter.disable_active_model(task_name, reason="model_load_error")
        except Exception:
            pass
        return GovernanceCheckResult(ok=False, task_name=str(task_name or ""), recommended_action="force_legacy", reason="model_load_error")

    def handle_registry_inconsistent(self, task_name: str) -> GovernanceCheckResult:
        self.record_model_event(task_name=task_name, event_type="registry_inconsistent", severity="warning", message="registry inconsistent", action_taken="repair")
        try:
            if self.registry_adapter is not None:
                repair = self.registry_adapter.repair_registry(task_name)
                return GovernanceCheckResult(ok=bool(repair.get("ok", False)), task_name=str(task_name or ""), recommended_action="keep_shadow" if repair.get("ok", False) else "force_legacy", reason="registry_repair", raw_payload=repair)
        except Exception as exc:
            return GovernanceCheckResult(ok=False, task_name=str(task_name or ""), recommended_action="force_legacy", reason=f"registry_repair_exception:{exc}")
        return GovernanceCheckResult(ok=False, task_name=str(task_name or ""), recommended_action="force_legacy", reason="registry_adapter_unavailable")

    def record_model_event(self, **kwargs: Any) -> dict[str, Any]:
        try:
            if self.event_logger is not None:
                return self.event_logger.record(**kwargs)
        except Exception:
            pass
        return {}

    def write_status(self, state: Any) -> bool:
        try:
            if self.status_writer is not None:
                return self.status_writer.write_task(state)
        except Exception:
            pass
        return False

    def startup_check(self) -> dict[str, Any]:
        warnings: list[str] = []
        errors: list[str] = []
        if not self.available:
            return {"ok": False, "warnings": ["governance_unavailable"], "errors": []}
        try:
            self.record_model_event(event_type="governance_startup_check", severity="info", message="governance startup check", action_taken="check")
            if self.registry_adapter is not None:
                consistency = self.registry_adapter.check_registry_consistency()
                if not consistency.get("ok", False):
                    warnings.append("registry_inconsistent")
                    repair = self.registry_adapter.repair_registry()
                    if not repair.get("ok", False):
                        errors.append("registry_repair_failed")
            return {"ok": not errors, "warnings": warnings, "errors": errors}
        except Exception as exc:
            return {"ok": False, "warnings": warnings + [f"governance_startup_exception:{exc}"], "errors": errors}

    def guard_config(self, effective_config: Any) -> dict[str, Any]:
        warnings: list[str] = []
        disabled_flags: list[str] = []
        for task, flag in FLAG_BY_TASK.items():
            if task == "outcome":
                continue
            if bool(getattr(effective_config, flag, False)):
                decision_type = {"sc": "sc_fallback", "parent": "parent_selection", "policy": "mutation_policy", "simulator": "simulator_skip"}.get(task, task)
                decision = self.allow_hard_decision(task, decision_type, effective_config)
                if not decision.allowed:
                    try:
                        setattr(effective_config, flag, False)
                    except Exception:
                        pass
                    disabled_flags.append(flag)
                    warnings.append(f"{flag} disabled by governance: {decision.reason}")
                elif decision.warnings:
                    warnings.extend(decision.warnings)
        return {"effective_config": effective_config, "warnings": warnings, "disabled_flags": disabled_flags}


AutonomyGovernanceService = LearningGovernanceService
