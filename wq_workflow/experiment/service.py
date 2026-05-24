from __future__ import annotations

import hashlib
from typing import Any

from .assignment import make_assignment
from .budget import ArmRecommendation, ExperimentBudgetAllocator, ExperimentBudgetPlan, snapshot_from_plan
from .planner import DefaultExperimentPlanner, context_to_dict
from .repository import ExperimentRepository
from .reporter import ExperimentReporter
from .schema import ExperimentAssignment, ExperimentArm, ExperimentPlan, ExperimentResult, utc_now_iso


class ExperimentService:
    def __init__(
        self,
        *,
        config: Any | None = None,
        repository: ExperimentRepository | None = None,
        reporter: ExperimentReporter | None = None,
        planner: DefaultExperimentPlanner | None = None,
        storage: Any | None = None,
        db_path: Any | None = None,
        logger: Any | None = None,
    ) -> None:
        self.config = config
        self.logger = logger
        self.enabled = bool(getattr(config, "enable_experiment_tracking", True))
        self.planner = planner or DefaultExperimentPlanner(config=config)
        self.budget_allocator = ExperimentBudgetAllocator(config=config, logger=logger)
        self.repository = repository or ExperimentRepository(storage=storage, db_path=db_path, logger=logger)
        status_path = getattr(config, "experiment_status_path", "runtime/status/experiment_report.json")
        self.reporter = reporter or ExperimentReporter(repository=self.repository, status_path=status_path, logger=logger)
        self.available = True
        self.warnings: list[str] = []

    def startup_check(self) -> dict[str, Any]:
        if not self.enabled:
            return {"ok": True, "enabled": False, "tracking_only": True}
        try:
            init_result = self.repository.initialize()
            if not init_result.get("ok", False):
                self.available = False
                self._warn(str(init_result.get("error") or "repository_initialize_failed"))
                return {"ok": False, "enabled": True, "available": False, "warnings": list(self.warnings)}
            plan = self.ensure_default_plan()
            return {
                "ok": plan is not None,
                "enabled": True,
                "available": self.available,
                "default_experiment_id": getattr(plan, "experiment_id", self.planner.default_experiment_id),
                "tracking_only": True,
                "warnings": list(self.warnings),
            }
        except Exception as exc:
            self.available = False
            self._warn(f"startup_check_failed: {exc}")
            return {"ok": False, "enabled": True, "available": False, "warnings": list(self.warnings)}

    def ensure_default_plan(self) -> ExperimentPlan | None:
        if not self.enabled:
            return None
        try:
            experiment_id = self.planner.default_experiment_id
            existing = self.repository.get_plan(experiment_id)
            if existing is not None:
                if existing.status != "active":
                    existing.status = "active"
                    existing.updated_at = utc_now_iso()
                    self.repository.save_plan(existing)
                return existing
            plan = self.planner.build_default_plan()
            result = self.repository.save_plan(plan)
            if not result.get("ok", False):
                self._warn(str(result.get("error") or "save_default_plan_failed"))
                return None
            return plan
        except Exception as exc:
            self._warn(f"ensure_default_plan_failed: {exc}")
            return None

    def assign_candidate(self, candidate_context: Any) -> ExperimentAssignment | None:
        if not self.enabled or not self.available:
            return None
        try:
            data = context_to_dict(candidate_context)
            plan = self.ensure_default_plan()
            if plan is None:
                return None
            arm = self.planner.infer_arm({**data, "experiment_id": plan.experiment_id})
            recommendation = self.recommend_arm(data) if str(getattr(self.config, "experiment_assignment_mode", "tracking_only")) == "advisory_budget" else None
            if recommendation is not None:
                data["budget_plan_id"] = recommendation.raw_payload.get("budget_plan_id")
                data["budget_suggested_ratio"] = recommendation.suggested_ratio
                data["budget_reason_codes"] = list(recommendation.reason_codes)
                data["budget_recommended_arm_id"] = recommendation.arm_id
            self._ensure_arm(plan, arm)
            assignment = make_assignment(plan.experiment_id, arm.arm_id, data, assigned_by=str(data.get("assigned_by") or "default_planner"))
            result = self.repository.save_assignment(assignment)
            if not result.get("ok", False):
                self._warn(str(result.get("error") or "save_assignment_failed"))
                return None
            return assignment
        except Exception as exc:
            self._warn(f"assign_candidate_failed: {exc}")
            return None

    def record_result(self, alpha_id: str, result_context: Any) -> ExperimentResult | None:
        if not self.enabled or not self.available or not alpha_id:
            return None
        try:
            assignment = self.repository.find_assignment_by_alpha(alpha_id)
            if assignment is None:
                self._warn(f"assignment_not_found: {alpha_id}")
                return None
            data = context_to_dict(result_context)
            metrics = data.get("metrics") if isinstance(data.get("metrics"), dict) else {}
            quality = data.get("quality")
            quality_dict = context_to_dict(quality)
            platform_sc = data.get("platform_sc") if isinstance(data.get("platform_sc"), dict) else {}
            platform_sc_abs_max = _pick_float(data, "platform_sc_abs_max", metrics=platform_sc)
            if platform_sc_abs_max is None:
                platform_sc_abs_max = _pick_float(metrics, "platform_sc_abs_max")
            result = ExperimentResult(
                result_id=str(data.get("result_id") or _result_id(assignment.assignment_id, alpha_id)),
                assignment_id=assignment.assignment_id,
                experiment_id=assignment.experiment_id,
                arm_id=assignment.arm_id,
                alpha_id=alpha_id,
                success=_pick_bool(data, "success", default=_pick_bool(data, "ok", default=None)),
                reward=_pick_float(data, "reward", metrics=metrics),
                sharpe=_pick_float(data, "sharpe", metrics=metrics),
                fitness=_pick_float(data, "fitness", metrics=metrics),
                returns=_pick_float(data, "returns", metrics=metrics),
                turnover=_pick_float(data, "turnover", metrics=metrics),
                drawdown=_pick_float(data, "drawdown", metrics=metrics),
                margin=_pick_float(data, "margin", metrics=metrics),
                platform_sc_status=_pick_text(data, "platform_sc_status") or _pick_text(platform_sc, "status"),
                platform_sc_abs_max=platform_sc_abs_max,
                quality_passed=_pick_bool(data, "quality_passed", default=_pick_bool(quality_dict, "passed", default=None)),
                failure_type=_pick_text(data, "failure_type") or _pick_text(data, "failure_reason"),
                raw_payload=data,
            )
            saved = self.repository.save_result(result)
            if not saved.get("ok", False):
                self._warn(str(saved.get("error") or "save_result_failed"))
                return None
            self.repository.update_summary(result.experiment_id, result.arm_id)
            return result
        except Exception as exc:
            self._warn(f"record_result_failed: {exc}")
            return None

    def generate_budget_plan(self, experiment_id: str | None = None, total_budget_hint: int | None = None) -> ExperimentBudgetPlan | None:
        if not self.enabled or not self.available:
            return None
        try:
            plan_id = str(experiment_id or getattr(self.config, "default_experiment_id", self.planner.default_experiment_id) or self.planner.default_experiment_id)
            if total_budget_hint is None:
                try:
                    total_budget_hint = int(getattr(self.config, "experiment_budget_total_hint", 200))
                except (TypeError, ValueError):
                    total_budget_hint = 200
            summaries = self.repository.list_summaries(plan_id)
            budget_plan = self.budget_allocator.build_budget_plan(
                plan_id,
                summaries,
                total_budget_hint=total_budget_hint,
                governance_service=getattr(self, "governance_service", None),
            )
            saved = self.repository.save_budget_plan(budget_plan)
            if not saved.get("ok", False):
                self._warn(str(saved.get("error") or "save_budget_plan_failed"))
                return None
            snapshot = snapshot_from_plan(budget_plan)
            snapshot_saved = self.repository.save_budget_snapshot(snapshot)
            if not snapshot_saved.get("ok", False):
                self._warn(str(snapshot_saved.get("error") or "save_budget_snapshot_failed"))
            self.update_report()
            return budget_plan
        except Exception as exc:
            self._warn(f"generate_budget_plan_failed: {exc}")
            return None

    def get_current_budget_plan(self, experiment_id: str | None = None) -> ExperimentBudgetPlan | None:
        try:
            plan_id = str(experiment_id or getattr(self.config, "default_experiment_id", self.planner.default_experiment_id) or self.planner.default_experiment_id)
            return self.repository.get_latest_budget_plan(plan_id)
        except Exception as exc:
            self._warn(f"get_current_budget_plan_failed: {exc}")
            return None

    def recommend_arm(self, candidate_context: Any | None = None) -> ArmRecommendation | None:
        try:
            data = context_to_dict(candidate_context)
            experiment_id = str(data.get("experiment_id") or getattr(self.config, "default_experiment_id", self.planner.default_experiment_id) or self.planner.default_experiment_id)
            plan = self.get_current_budget_plan(experiment_id)
            if plan is None or not plan.allocations:
                return None
            eligible = [
                allocation
                for allocation in plan.allocations
                if allocation.governance_allowed and allocation.status not in {"disabled", "governance_blocked"} and allocation.suggested_ratio > 0
            ]
            if not eligible:
                return None
            allocation = sorted(eligible, key=lambda item: item.suggested_ratio, reverse=True)[0]
            return ArmRecommendation(
                recommendation_id=f"arm_recommendation:{plan.budget_plan_id}:{allocation.arm_id}",
                experiment_id=plan.experiment_id,
                arm_id=allocation.arm_id,
                suggested_ratio=allocation.suggested_ratio,
                reason_codes=list(allocation.reason_codes),
                raw_payload={"budget_plan_id": plan.budget_plan_id, "mode": "advisory"},
            )
        except Exception as exc:
            self._warn(f"recommend_arm_failed: {exc}")
            return None

    def update_report(self) -> dict[str, Any]:
        if not self.enabled or not self.available:
            return {"ok": True, "enabled": self.enabled, "available": self.available, "skipped": True}
        try:
            for plan in self.repository.get_active_plans():
                for arm in plan.arms:
                    self.repository.update_summary(plan.experiment_id, arm.arm_id)
            return self.reporter.update(warnings=list(self.warnings))
        except Exception as exc:
            self._warn(f"update_report_failed: {exc}")
            return {"ok": False, "error": str(exc), "warnings": list(self.warnings)}

    def _ensure_arm(self, plan: ExperimentPlan, arm: ExperimentArm) -> None:
        if any(existing.arm_id == arm.arm_id for existing in plan.arms):
            return
        plan.arms.append(arm)
        plan.updated_at = utc_now_iso()
        saved = self.repository.save_plan(plan)
        if not saved.get("ok", False):
            self._warn(str(saved.get("error") or "save_arm_failed"))

    def _warn(self, message: str) -> None:
        self.warnings.append(message)
        self.warnings = self.warnings[-50:]
        if self.logger is not None:
            try:
                self.logger.warning("experiment service: %s", message)
            except Exception:
                pass


def _result_id(assignment_id: str, alpha_id: str) -> str:
    digest = hashlib.sha256(f"{assignment_id}|{alpha_id}".encode("utf-8", errors="replace")).hexdigest()[:24]
    return f"result:{digest}"


def _pick_float(data: dict[str, Any], key: str, *, metrics: dict[str, Any] | None = None) -> float | None:
    value = data.get(key)
    if value is None and metrics:
        value = metrics.get(key)
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number in {float("inf"), float("-inf")}:
        return None
    return number


def _pick_bool(data: dict[str, Any], key: str, *, default: bool | None = None) -> bool | None:
    value = data.get(key)
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on", "pass", "passed", "success"}:
        return True
    if text in {"0", "false", "no", "n", "off", "fail", "failed"}:
        return False
    return default


def _pick_text(data: dict[str, Any], key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    text = str(value)
    return text if text else None
