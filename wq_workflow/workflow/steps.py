from __future__ import annotations

from typing import Any

from .result import StepResult


class BaseStep:
    name = "BASE"
    is_critical = False
    is_observe_only = False

    def __init__(self, app_context: Any):
        self.ctx = app_context

    def run(self, wf: Any) -> StepResult:
        raise NotImplementedError

    def attach_alpha_representation(self, wf: Any) -> None:
        if not bool(getattr(getattr(self.ctx, "config", None), "enable_alpha_representation", True)):
            return
        candidate = getattr(wf, "candidate", None) or {}
        expression = ""
        if isinstance(candidate, dict):
            expression = str(candidate.get("expression") or candidate.get("code") or "")
        if not expression:
            return
        if getattr(wf, "alpha_representation", None) is not None:
            return
        try:
            builder = getattr(self.ctx, "alpha_services", {}).get("build_representation") if hasattr(self.ctx, "alpha_services") else None
            if builder is None:
                from wq_workflow.alpha.representation.features import build_alpha_representation

                builder = build_alpha_representation
            wf.alpha_representation = builder(expression)
        except Exception:
            return


class PrepareIterationStep(BaseStep):
    name = "PREPARE_ITERATION"

    def run(self, wf: Any) -> StepResult:
        return StepResult(ok=True, message="observe-only prepare")


class SelectStrategyStep(BaseStep):
    name = "SELECT_STRATEGY"

    def run(self, wf: Any) -> StepResult:
        portfolio = self.ctx.strategy_services.get("portfolio")
        strategy = portfolio.select_strategy(task_name=getattr(wf, "task_name", None)) if portfolio else {"strategy_id": "legacy_champion", "strategy_type": "legacy"}
        wf.strategy = strategy
        if portfolio is not None:
            try:
                portfolio.record_strategy_decision(strategy, {"alpha_id": wf.alpha_id or "", "iteration_id": wf.iteration_id, "decision_type": "strategy_selection"}, selected=True, shadow=False, score=None)
            except Exception:
                pass
        return StepResult(data={"strategy": strategy})


class SelectParentStep(BaseStep):
    name = "SELECT_PARENT"

    def run(self, wf: Any) -> StepResult:
        policy = getattr(self.ctx, "learning_services", {}).get("parent_policy")
        available = []
        if wf.parent:
            available.append(wf.parent)
        elif wf.candidate:
            available.append(wf.candidate)
        context = {"alpha_id": wf.alpha_id or "", "iteration_id": wf.iteration_id}
        chosen = None
        if policy is not None:
            try:
                chosen = policy.select_parent(available, context=context, workflow_context=wf)
            except Exception:
                chosen = available[0] if available else None
        else:
            chosen = available[0] if available else None
        wf.parent = chosen
        try:
            shadow = getattr(wf, "parent_shadow_ranking", []) or []
            if wf.decisions:
                wf.decisions[-1]["strategy_id"] = (wf.strategy or {}).get("strategy_id", "legacy_champion")
                wf.decisions[-1]["model_recommended_parent"] = shadow[0] if shadow else None
                wf.decisions[-1]["legacy_selected_parent"] = chosen
                wf.decisions[-1]["model_legacy_match"] = bool(shadow and shadow[0] == chosen)
        except Exception:
            pass
        return StepResult(data={"parent": chosen}, message="parent learning shadow; legacy parent preserved")


class PlanExperimentStep(BaseStep):
    name = "PLAN_EXPERIMENT"

    def run(self, wf: Any) -> StepResult:
        planner = self.ctx.learning_services.get("experiment_planner")
        experiment = planner.plan(wf.parent, wf.alpha_representation, wf.strategy) if planner else None
        wf.experiment = experiment
        return StepResult(data={"experiment": experiment} if experiment else {}, message="observe-only experiment metadata")


class GenerateCandidateStep(BaseStep):
    name = "GENERATE_CANDIDATE"

    def run(self, wf: Any) -> StepResult:
        self.attach_alpha_representation(wf)
        policy = getattr(self.ctx, "learning_services", {}).get("policy_policy")
        actions = []
        if wf.candidate:
            actions.append({"action_id": "legacy_candidate", "action_type": wf.candidate.get("mutation_type") if isinstance(wf.candidate, dict) else "legacy", "legacy_score": wf.reward or 0.0})
        if policy is not None and actions:
            try:
                policy.choose_action(actions, legacy_action=actions[0], context={"alpha_id": wf.alpha_id or "", "iteration_id": wf.iteration_id}, workflow_context=wf)
            except Exception:
                pass
        return StepResult(message="legacy placeholder; policy shadow only")


class LocalPrecheckStep(BaseStep):
    name = "LOCAL_PRECHECK"

    def run(self, wf: Any) -> StepResult:
        self.attach_alpha_representation(wf)
        wf.local_checks.setdefault("observe_only", True)
        outcome_policy = getattr(self.ctx, "learning_services", {}).get("outcome_policy")
        if outcome_policy is not None:
            try:
                candidate = wf.candidate or {}
                features = dict(candidate.get("features") or {}) if isinstance(candidate, dict) else {}
                rep = getattr(wf, "alpha_representation", None)
                if rep is not None:
                    features.update(getattr(rep, "features", {}) or {})
                result = outcome_policy.evaluate_candidate(candidate, features=features, context={"alpha_id": wf.alpha_id or "", "iteration_id": wf.iteration_id})
                wf.simulator_prediction = result.get("prediction", {}) if isinstance(result, dict) else {}
                wf.local_checks["simulator_should_skip"] = False
                wf.local_checks["simulator_policy"] = result
                decision_logger = getattr(self.ctx, "offline_services", {}).get("decision_snapshot_logger")
                if decision_logger is not None:
                    decision_id = decision_logger.record(
                        decision_type="simulator_decision",
                        alpha_id=wf.alpha_id or "",
                        context={"alpha_id": wf.alpha_id or "", "iteration_id": wf.iteration_id, "strategy_id": (wf.strategy or {}).get("strategy_id", "legacy_champion")},
                        available_actions=[{"action_id": "run_backtest", "action_type": "simulator_run"}, {"action_id": "skip_backtest", "action_type": "simulator_skip"}],
                        chosen_action={"action_id": "run_backtest", "action_type": "simulator_run"},
                        action_scores={"run_backtest": 1.0, "skip_backtest": float((wf.simulator_prediction or {}).get("skip_risk", 0.0) or 0.0)},
                        selection_reason="simulator_model_observe_only_legacy_run",
                        model_score=float((wf.simulator_prediction or {}).get("skip_risk", 0.0) or 0.0),
                        model_version=str((wf.simulator_prediction or {}).get("model_version", "")),
                    )
                    wf.decisions.append({"decision_id": decision_id, "decision_type": "simulator_decision", "alpha_id": wf.alpha_id or "", "chosen_action": {"action_id": "run_backtest"}, "strategy_id": (wf.strategy or {}).get("strategy_id", "legacy_champion")})
            except Exception:
                wf.local_checks["simulator_should_skip"] = False
        return StepResult(data={"local_checks": wf.local_checks})


class SubmitBacktestStep(BaseStep):
    name = "SUBMIT_BACKTEST"
    is_critical = True
    is_observe_only = True

    def run(self, wf: Any) -> StepResult:
        return StepResult(message="observe-only; does not submit backtest")


class WaitResultStep(BaseStep):
    name = "WAIT_RESULT"
    is_critical = True
    is_observe_only = True

    def run(self, wf: Any) -> StepResult:
        return StepResult(message="observe-only; does not wait for platform")


class ParseResultStep(BaseStep):
    name = "PARSE_RESULT"
    is_critical = True
    is_observe_only = True

    def run(self, wf: Any) -> StepResult:
        return StepResult(message="observe-only; parser wrapper placeholder")


class CollectPlatformSCStep(BaseStep):
    name = "COLLECT_PLATFORM_SC"
    is_critical = True
    is_observe_only = True

    def run(self, wf: Any) -> StepResult:
        return StepResult(message="observe-only; no page available")


class QualityCheckStep(BaseStep):
    name = "QUALITY_CHECK"

    def run(self, wf: Any) -> StepResult:
        return StepResult(message="observe-only; reward semantics unchanged")


class RewardStep(BaseStep):
    name = "REWARD"
    is_critical = True
    is_observe_only = True

    def run(self, wf: Any) -> StepResult:
        return StepResult(message="observe-only; no reward calculation")


class PersistResultStep(BaseStep):
    name = "PERSIST_RESULT"

    def run(self, wf: Any) -> StepResult:
        uow = self.ctx.data_services.get("unit_of_work") if hasattr(self.ctx, "data_services") else None
        if not uow:
            return StepResult(data={"persisted": False}, message="unit of work unavailable")
        result = uow.persist_result(wf)
        fatal = bool(result.get("fatal"))
        persisted = not fatal
        return StepResult(ok=not fatal, fatal=fatal, data={"persisted": persisted, "persist_result": result}, message="persisted via unit of work")


class LearningSampleStep(BaseStep):
    name = "LEARNING_SAMPLE"

    def run(self, wf: Any) -> StepResult:
        services = getattr(self.ctx, "learning_services", {})
        logger = getattr(self.ctx, "logger", None)
        results: dict[str, Any] = {}

        candidate = wf.candidate or {}
        metrics = wf.metrics or {}
        expression = str(candidate.get("expression") or candidate.get("code") or "")
        features = dict(candidate.get("features") or {})
        rep = getattr(wf, "alpha_representation", None)
        if rep is not None:
            try:
                features.update(getattr(rep, "features", {}) or {})
                features["alpha_representation"] = rep
            except Exception:
                pass
        for key in ("sharpe", "fitness", "turnover", "margin"):
            if key in metrics:
                features.setdefault(key, metrics.get(key))
        features.setdefault("estimated_self_corr", candidate.get("estimated_self_corr"))
        context = {
            "alpha_id": wf.alpha_id or candidate.get("alpha_id", ""),
            "expression": expression,
            "behavior_family": candidate.get("behavior_family"),
            "mutation_type": candidate.get("mutation_type"),
            "candidate_source": candidate.get("candidate_source"),
        }

        calls = [
            (
                "sc",
                lambda: services.get("sc_sample_store").record_if_complete(
                    alpha_id=wf.alpha_id or candidate.get("alpha_id", ""),
                    expression=expression,
                    platform_sc=wf.platform_sc,
                    features=features,
                    context=context,
                    raw_payload={"candidate": candidate, "metrics": metrics, "platform_sc": wf.platform_sc},
                )
                if services.get("sc_sample_store")
                else None,
            ),
            (
                "parent",
                lambda: services.get("parent_sample_store").record_parent_outcome(wf.parent, candidate, wf)
                if services.get("parent_sample_store")
                else None,
            ),
            (
                "policy",
                lambda: services.get("policy_sample_store").record_policy_outcome(getattr(wf, "policy_decision_id", None), wf)
                if services.get("policy_sample_store")
                else None,
            ),
            (
                "simulator",
                lambda: services.get("outcome_sample_store").record_simulator_outcome(candidate, getattr(wf, "simulator_prediction", {}), wf)
                if services.get("outcome_sample_store")
                else None,
            ),
        ]
        for name, call in calls:
            try:
                results[name] = call()
            except Exception as exc:
                results[name] = {"error": str(exc)}
                try:
                    if logger:
                        logger.warning("learning sample step failed for %s: %s", name, exc)
                except Exception:
                    pass
        return StepResult(data={"learning_samples": results}, message="observe-only learning samples")


class PolicyUpdateStep(BaseStep):
    name = "POLICY_UPDATE"

    def run(self, wf: Any) -> StepResult:
        policy = getattr(self.ctx, "learning_services", {}).get("policy_policy")
        if policy is not None and wf.candidate:
            try:
                action = {"action_id": "legacy_policy_update", "action_type": (wf.candidate or {}).get("mutation_type"), "legacy_score": wf.reward or 0.0}
                policy.choose_action([action], legacy_action=action, context={"alpha_id": wf.alpha_id or "", "iteration_id": wf.iteration_id}, workflow_context=wf)
            except Exception:
                pass
        sample_store = getattr(self.ctx, "learning_services", {}).get("policy_sample_store")
        sample_id = None
        if sample_store is not None:
            try:
                sample_id = sample_store.record_policy_outcome(getattr(wf, "policy_decision_id", None), wf)
            except Exception:
                sample_id = None
        portfolio = getattr(self.ctx, "strategy_services", {}).get("portfolio")
        if portfolio is not None:
            try:
                portfolio.record_strategy_decision(wf.strategy or {"strategy_id": "legacy_champion"}, {"alpha_id": wf.alpha_id or "", "iteration_id": wf.iteration_id, "decision_type": "policy_update"}, selected=True, shadow=False, score=wf.reward)
            except Exception:
                pass
        return StepResult(data={"policy_outcome_sample_id": sample_id}, message="observe-only policy hook")


class MonitoringStep(BaseStep):
    name = "MONITORING"

    def run(self, wf: Any) -> StepResult:
        registry = getattr(self.ctx, "learning_services", {}).get("model_registry")
        model_status = {}
        if registry is not None:
            try:
                model_status = {task: bool(registry.load_active_model(task)) for task in ("sc", "parent", "policy", "simulator")}
            except Exception:
                model_status = {}
        if not getattr(self.ctx.config, "enable_drift_monitor", False):
            return StepResult(data={"monitoring": {"status": "skipped", "reason": "disabled", "models": model_status, **self._strategy_monitoring(wf)}})
        monitor = self.ctx.monitoring_services.get("drift_monitor")
        status = monitor.check() if monitor else {"status": "disabled"}
        drift_repo = getattr(self.ctx, "data_services", {}).get("repositories")
        try:
            if drift_repo is not None and hasattr(drift_repo, "drift") and isinstance(status, dict) and status.get("status") not in {"disabled", "skipped"}:
                drift_repo.drift.insert_drift_event({"drift_type": "monitoring", "severity": status.get("severity", "info"), "event": status})
        except Exception:
            pass
        if isinstance(status, dict):
            status.update(self._strategy_monitoring(wf))
        return StepResult(data={"monitoring": status})

    def _strategy_monitoring(self, wf: Any) -> dict[str, Any]:
        services = getattr(self.ctx, "strategy_services", {})
        out: dict[str, Any] = {}
        strategy_id = ((getattr(wf, "strategy", None) or {}).get("strategy_id") or "legacy_champion")
        tracker = services.get("performance_tracker")
        if tracker is not None:
            try:
                out["strategy_performance"] = tracker.update_strategy_performance(strategy_id)
            except Exception as exc:
                out["strategy_performance"] = {"updated": False, "error": str(exc)}
        promotion = services.get("promotion_policy")
        if promotion is not None and strategy_id != "legacy_champion":
            try:
                out["promotion"] = promotion.promote_if_eligible(strategy_id) if getattr(self.ctx.config, "enable_auto_promotion", False) else promotion.evaluate_promotion(strategy_id)
            except Exception as exc:
                out["promotion"] = {"promotion_pass": False, "error": str(exc)}
        rollback = services.get("rollback_policy")
        if rollback is not None:
            try:
                evaluation = rollback.evaluate_rollback(strategy_id)
                out["rollback"] = rollback.rollback_to_previous_champion(evaluation.get("reason", "auto_rollback")) if getattr(self.ctx.config, "enable_auto_rollback", False) and evaluation.get("rollback_pass") else evaluation
            except Exception as exc:
                out["rollback"] = {"rollback_pass": False, "error": str(exc)}
        return out


DEFAULT_STEP_CLASSES = [
    PrepareIterationStep,
    SelectStrategyStep,
    SelectParentStep,
    PlanExperimentStep,
    GenerateCandidateStep,
    LocalPrecheckStep,
    SubmitBacktestStep,
    WaitResultStep,
    ParseResultStep,
    CollectPlatformSCStep,
    QualityCheckStep,
    RewardStep,
    PersistResultStep,
    LearningSampleStep,
    PolicyUpdateStep,
    MonitoringStep,
]
