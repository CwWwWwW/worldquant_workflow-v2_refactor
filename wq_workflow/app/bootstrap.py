from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .context import AppContext


def build_app_context(config_path: str | Path | None = None, config: Any | None = None, *, logger: Any | None = None, storage: Any | None = None, candidate_pool: Any | None = None) -> AppContext:
    from wq_workflow import paths
    from wq_workflow.config import load_config

    # config_path is accepted for the v2 interface. The legacy loader still reads
    # the project config file; custom config objects remain supported for tests.
    config = config or load_config()
    logger = logger or logging.getLogger("wq_workflow.app")
    if storage is None and getattr(config, "enable_data_services", True):
        try:
            from wq_workflow.storage.manager import get_storage_manager
            storage = get_storage_manager()
            storage.initialize()
        except Exception as exc:
            logger.warning("storage initialization skipped: %s", exc)
            storage = None
    ctx = AppContext(config=config, paths=paths, logger=logger, storage=storage, candidate_pool=candidate_pool)

    if getattr(config, "enable_platform_services", True):
        from wq_workflow.platform.sc_collector import PlatformSCCollector
        from wq_workflow.platform.service import PlatformService

        ctx.platform_services["sc_collector"] = PlatformSCCollector(logger, timeout=int(getattr(config, "platform_sc_timeout_seconds", 90) or 90))
        ctx.platform_services["platform_service_factory"] = lambda page=None: PlatformService(page=page, config=ctx.config, logger=logger)

    from wq_workflow.alpha.representation.features import build_alpha_representation
    from wq_workflow.data.repositories import RepositoryBundle
    from wq_workflow.data.unit_of_work import IterationUnitOfWork
    from wq_workflow.learning.ml.model_registry import ModelRegistry
    from wq_workflow.learning.ml.prediction_audit import PredictionAuditLogger, PredictionAuditService
    from wq_workflow.learning.outcome.policy import OutcomeSimulatorPolicy
    from wq_workflow.learning.outcome.predictor import OutcomePredictor
    from wq_workflow.learning.outcome.trainer import OutcomeTrainer
    from wq_workflow.learning.outcome.sample_store import OutcomeSampleStore
    from wq_workflow.learning.parent.policy import ParentLearningPolicy
    from wq_workflow.learning.parent.predictor import ParentPredictor
    from wq_workflow.learning.parent.trainer import ParentTrainer
    from wq_workflow.learning.parent.sample_store import ParentSampleStore
    from wq_workflow.learning.policy.policy import ActionLearningPolicy
    from wq_workflow.learning.policy.predictor import PolicyPredictor
    from wq_workflow.learning.policy.trainer import PolicyTrainer
    from wq_workflow.learning.policy.sample_store import PolicySampleStore
    from wq_workflow.learning.sc.policy import SCLearningPolicy
    from wq_workflow.learning.sc.predictor import SCPredictor
    from wq_workflow.learning.sc.sample_store import SCSampleStore
    from wq_workflow.learning.sc.trainer import SCTrainer
    from wq_workflow.offline.decision_snapshot import DecisionOutcomeRecorder, DecisionSnapshotLogger
    from wq_workflow.offline.service import CounterfactualService, DecisionSnapshotService, OfflineReplayService
    from wq_workflow.offline.support_checker import SupportChecker
    from wq_workflow.strategy.budget_allocator import BudgetAllocator
    from wq_workflow.strategy.champion_challenger import ModelSafetyGate
    from wq_workflow.strategy.performance_tracker import PerformanceTracker
    from wq_workflow.strategy.portfolio import StrategyPortfolio
    from wq_workflow.strategy.promotion import PromotionPolicy
    from wq_workflow.strategy.registry import StrategyRegistry
    from wq_workflow.strategy.rollback import RollbackPolicy
    from wq_workflow.strategy.service import StrategyService
    from wq_workflow.strategy.portfolio_service import StrategyPortfolioService
    from wq_workflow.strategy.budget_service import StrategyBudgetService
    from wq_workflow.experiment.planner import ExperimentPlanner
    from wq_workflow.monitoring.drift_monitor import DriftMonitor
    from wq_workflow.learning.insight.feedback import InsightFeedbackRecorder
    from wq_workflow.adapters.legacy_orchestrator_adapter import run_legacy_orchestrator
    from wq_workflow.evaluation.quality_service import QualityService
    from wq_workflow.evaluation.reward_service import RewardService
    from wq_workflow.evaluation.sc_service import SCService
    from wq_workflow.evaluation.success_detector import SuccessDetector

    ctx.evaluation_services.update({
        "quality": QualityService(config=config),
        "reward": RewardService(config=config),
        "sc": SCService(),
        "success_detector": SuccessDetector(),
    })

    repositories = RepositoryBundle.from_storage(storage=storage)
    ctx.repositories = repositories
    unit_of_work = IterationUnitOfWork(repositories, logger=logger, storage=storage)
    try:
        from wq_workflow.experiment.service import ExperimentService

        experiment_service = ExperimentService(
            config=config,
            storage=storage,
            db_path=getattr(config, "storage_db_path", "runtime/db/workflow.db"),
            logger=logger,
        )
        ctx.experiment_service = experiment_service
        ctx.experiment_services["tracking"] = experiment_service
        ctx.runtime_status["experiment_tracking"] = experiment_service.startup_check()
    except Exception as exc:
        logger.warning("experiment tracking initialization skipped: %s", exc)
    model_root = Path(str(getattr(config, "ml_model_root", "runtime/models") or "runtime/models"))
    try:
        model_root_path = model_root if model_root.is_absolute() else paths.ROOT / model_root
    except Exception:
        model_root_path = paths.RUNTIME_DIR / "models"
    model_registry = ModelRegistry(storage=storage, model_root=model_root_path, logger=logger)
    governance_service = None
    if bool(getattr(config, "enable_learning_governance", True)):
        try:
            from wq_workflow.governance.service import LearningGovernanceService

            governance_service = LearningGovernanceService(config=config, model_registry=model_registry, storage=storage, model_root=model_root_path, logger=logger)
        except Exception as exc:
            logger.warning("learning governance service initialization skipped: %s", exc)
    try:
        from wq_workflow.app.config_guard import apply_config_safety_gate

        guard_result = apply_config_safety_gate(config, model_registry=model_registry, governance_service=governance_service, logger=logger)
        config = guard_result.get("effective_config", config)
        ctx.config = config
        if governance_service is not None:
            governance_service.config = config
        ctx.runtime_status["config_safety_gate"] = guard_result
    except Exception as exc:
        logger.warning("config safety gate skipped: %s", exc)
    decision_snapshot_service = None
    if bool(getattr(config, "enable_decision_snapshots", True)):
        try:
            decision_snapshot_service = DecisionSnapshotService(
                config=config,
                storage=storage,
                db_path=getattr(config, "storage_db_path", "runtime/db/workflow.db"),
                logger=logger,
            )
            ctx.decision_snapshot_service = decision_snapshot_service
            ctx.offline_services["decision_snapshot"] = decision_snapshot_service
            ctx.runtime_status["offline"] = {"decision_snapshot": decision_snapshot_service.startup_check()}
        except Exception as exc:
            logger.warning("decision snapshot initialization skipped: %s", exc)
            decision_snapshot_service = None
    offline_replay_service = None
    try:
        offline_replay_service = OfflineReplayService(
            config=config,
            storage=storage,
            db_path=getattr(config, "storage_db_path", "runtime/db/workflow.db"),
            logger=logger,
        )
        ctx.offline_replay_service = offline_replay_service
        ctx.offline_services["replay"] = offline_replay_service
        ctx.runtime_status.setdefault("offline", {})["replay"] = offline_replay_service.startup_check()
    except Exception as exc:
        logger.warning("offline replay service initialization skipped: %s", exc)
        offline_replay_service = None
    counterfactual_service = None
    try:
        counterfactual_service = CounterfactualService(
            config=config,
            storage=storage,
            db_path=getattr(config, "storage_db_path", "runtime/db/workflow.db"),
            logger=logger,
        )
        ctx.counterfactual_service = counterfactual_service
        ctx.offline_services["counterfactual"] = counterfactual_service
        ctx.runtime_status.setdefault("offline", {})["counterfactual"] = counterfactual_service.startup_check()
    except Exception as exc:
        logger.warning("counterfactual service initialization skipped: %s", exc)
        counterfactual_service = None
    if getattr(ctx, "experiment_service", None) is not None:
        try:
            ctx.experiment_service.config = config
            ctx.experiment_service.governance_service = governance_service
            ctx.experiment_service.decision_snapshot_service = decision_snapshot_service
            if getattr(config, "enable_experiment_budgeting", True) or getattr(config, "enable_experiment_design", True):
                ctx.experiment_service.generate_budget_plan(total_budget_hint=getattr(config, "experiment_budget_total_hint", None))
        except Exception as exc:
            logger.warning("experiment budgeting startup skipped: %s", exc)
    audit_logger = PredictionAuditLogger(repository=repositories.ml, storage=storage, logger=logger)
    prediction_audit = PredictionAuditService(repository=repositories.ml, storage=storage, logger=logger)
    decision_logger = DecisionSnapshotLogger(repository=repositories.decision, storage=storage, logger=logger)
    decision_outcome = DecisionOutcomeRecorder(repository=repositories.decision, storage=storage, logger=logger)
    support_checker = SupportChecker(repositories, config, logger)
    replay_evaluator = None
    counterfactual_estimator = None
    if bool(getattr(config, "enable_offline_replay", False)):
        try:
            from wq_workflow.offline.replay import OfflineReplayEvaluator

            replay_evaluator = OfflineReplayEvaluator(repositories, model_registry, config, logger)
        except Exception as exc:
            logger.warning("offline replay initialization skipped: %s", exc)
    if bool(getattr(config, "enable_counterfactual_evaluation", False)):
        try:
            from wq_workflow.offline.counterfactual import CounterfactualEstimator

            counterfactual_estimator = CounterfactualEstimator(repositories, config, logger)
        except Exception as exc:
            logger.warning("counterfactual initialization skipped: %s", exc)
    sc_predictor = SCPredictor(model_registry=model_registry, audit_logger=audit_logger, config=config)
    parent_predictor = ParentPredictor(model_registry=model_registry, audit_logger=audit_logger, config=config)
    policy_predictor = PolicyPredictor(model_registry=model_registry, audit_logger=audit_logger, config=config)
    outcome_predictor = OutcomePredictor(model_registry=model_registry, audit_logger=audit_logger, config=config)
    sc_sample_store = SCSampleStore(storage=storage, ml_repository=repositories.ml, logger=logger, config=config)
    parent_sample_store = ParentSampleStore(storage=storage, logger=logger, config=config)
    policy_sample_store = PolicySampleStore(storage=storage, logger=logger, config=config)
    outcome_sample_store = OutcomeSampleStore(storage=storage, logger=logger, config=config)
    ctx.alpha_services["build_representation"] = build_alpha_representation
    ctx.data_services.update({
        "repositories": repositories,
        "ml_repository": repositories.ml,
        "decision_repository": repositories.decision,
    })
    if storage is not None:
        ctx.data_services["unit_of_work"] = unit_of_work
    ctx.offline_services.update({
        "decision_snapshot_logger": decision_logger,
        "decision_outcome_recorder": decision_outcome,
        "decision_snapshot": decision_snapshot_service,
        "counterfactual_estimator": counterfactual_estimator,
        "counterfactual": counterfactual_service,
        "support_checker": support_checker,
        "replay_evaluator": replay_evaluator,
        "replay": offline_replay_service,
    })
    ctx.learning_services.update({
        "model_registry": model_registry,
        "prediction_audit": prediction_audit,
        "prediction_audit_logger": audit_logger,
        "decision_snapshot": decision_logger,
        "governance_service": governance_service,
        "sc_sample_store": sc_sample_store,
        "sc_predictor": sc_predictor,
        "sc_policy": SCLearningPolicy(config=config, predictor=sc_predictor, governance_service=governance_service),
        "sc_trainer": SCTrainer(storage=storage, model_registry=model_registry, config=config, logger=logger, repository=repositories.ml),
        "parent_predictor": parent_predictor,
        "parent_trainer": ParentTrainer(storage=storage, model_registry=model_registry, config=config, logger=logger),
        "parent_policy": ParentLearningPolicy(config=config, decision_logger=decision_logger, predictor=parent_predictor, audit_logger=audit_logger, governance_service=governance_service),
        "parent_sample_store": parent_sample_store,
        "policy_predictor": policy_predictor,
        "policy_trainer": PolicyTrainer(storage=storage, model_registry=model_registry, config=config, logger=logger),
        "policy_policy": ActionLearningPolicy(config=config, decision_logger=decision_logger, predictor=policy_predictor, audit_logger=audit_logger, governance_service=governance_service),
        "policy_sample_store": policy_sample_store,
        "outcome_predictor": outcome_predictor,
        "outcome_trainer": OutcomeTrainer(storage=storage, model_registry=model_registry, config=config, logger=logger),
        "outcome_policy": OutcomeSimulatorPolicy(config=config, predictor=outcome_predictor, audit_logger=prediction_audit, governance_service=governance_service),
        "outcome_sample_store": outcome_sample_store,
        "experiment_planner": ExperimentPlanner(config=config),
        "insight_feedback": InsightFeedbackRecorder(storage=storage, logger=logger),
    })
    strategy_registry = StrategyRegistry(repositories, config, logger)
    try:
        strategy_registry.ensure_default_strategies()
    except Exception as exc:
        logger.warning("default strategy initialization skipped: %s", exc)
    budget_allocator = BudgetAllocator(config, logger)
    performance_tracker = PerformanceTracker(repositories, config, logger)
    promotion_policy = PromotionPolicy(repositories, replay_evaluator, support_checker, config, logger)
    rollback_policy = RollbackPolicy(repositories, performance_tracker, config, logger)
    safety_gate = ModelSafetyGate(repositories, config, logger, model_registry=model_registry, support_checker=support_checker)
    strategy_portfolio = StrategyPortfolio(
        registry=strategy_registry,
        budget_allocator=budget_allocator,
        performance_tracker=performance_tracker,
        promotion_policy=promotion_policy,
        rollback_policy=rollback_policy,
        config=config,
        logger=logger,
        repositories=repositories,
    )
    ctx.strategy_services.update({
        "registry": strategy_registry,
        "budget_allocator": budget_allocator,
        "portfolio": strategy_portfolio,
        "promotion_policy": promotion_policy,
        "rollback_policy": rollback_policy,
        "performance_tracker": performance_tracker,
        "safety_gate": safety_gate,
    })
    if bool(getattr(config, "enable_strategy_registry", True)):
        try:
            strategy_service = StrategyService(
                config=config,
                storage=storage,
                db_path=getattr(config, "storage_db_path", "runtime/db/workflow.db"),
                logger=logger,
            )
            ctx.strategy_service = strategy_service
            ctx.strategy_services["service"] = strategy_service
            ctx.strategy_services["scoreboard_service"] = strategy_service
            ctx.runtime_status["strategy_registry"] = strategy_service.startup_check()
        except Exception as exc:
            logger.warning("strategy registry initialization skipped: %s", exc)
            ctx.runtime_status["strategy_registry"] = {"ok": bool(getattr(config, "strategy_fail_open", True)), "enabled": True, "fail_open": True, "error": str(exc)}
    else:
        ctx.runtime_status["strategy_registry"] = {"ok": True, "enabled": False}
    try:
        strategy_portfolio_service = StrategyPortfolioService(
            config=config,
            storage=storage,
            db_path=getattr(config, "storage_db_path", "runtime/db/workflow.db"),
            logger=logger,
            strategy_service=getattr(ctx, "strategy_service", None),
            governance_service=governance_service,
        )
        ctx.strategy_portfolio_service = strategy_portfolio_service
        ctx.strategy_services["legacy_portfolio"] = strategy_portfolio
        ctx.strategy_services["portfolio"] = strategy_portfolio_service
        ctx.strategy_services["portfolio_service"] = strategy_portfolio_service
        ctx.runtime_status["strategy_portfolio"] = strategy_portfolio_service.startup_check()
    except Exception as exc:
        logger.warning("strategy portfolio initialization skipped: %s", exc)
        ctx.runtime_status["strategy_portfolio"] = {"ok": bool(getattr(config, "strategy_portfolio_fail_open", True)), "enabled": bool(getattr(config, "enable_strategy_champion_challenger", False)), "fail_open": True, "error": str(exc)}
    try:
        strategy_budget_service = StrategyBudgetService(
            config=config,
            storage=storage,
            db_path=getattr(config, "storage_db_path", "runtime/db/workflow.db"),
            logger=logger,
            portfolio_service=getattr(ctx, "strategy_portfolio_service", None),
            governance_service=governance_service,
        )
        ctx.strategy_budget_service = strategy_budget_service
        ctx.strategy_services["budget"] = strategy_budget_service
        ctx.strategy_services["budget_service"] = strategy_budget_service
        ctx.runtime_status["strategy_budget"] = strategy_budget_service.startup_check()
    except Exception as exc:
        logger.warning("strategy budget initialization skipped: %s", exc)
        ctx.runtime_status["strategy_budget"] = {"ok": bool(getattr(config, "strategy_budget_fail_open", True)), "enabled": bool(getattr(config, "enable_strategy_budget_allocator", False)), "fail_open": True, "error": str(exc)}
    try:
        from wq_workflow.observability.service import ObservabilityService

        observability_service = ObservabilityService(
            config=config,
            storage=storage,
            db_path=getattr(config, "storage_db_path", "runtime/db/workflow.db"),
            logger=logger,
        )
        ctx.observability_service = observability_service
        ctx.observability_services["metrics"] = observability_service
        if bool(getattr(config, "enable_observability_metrics", True)):
            ctx.runtime_status["observability"] = observability_service.startup_check()
        else:
            ctx.runtime_status["observability"] = {"ok": True, "enabled": False, "mode": getattr(config, "observability_mode", "metrics_only")}
        try:
            from wq_workflow.observability.alert_diagnosis_service import AlertDiagnosisService

            alert_diagnosis_service = AlertDiagnosisService(
                config=config,
                storage=storage,
                db_path=getattr(config, "storage_db_path", "runtime/db/workflow.db"),
                logger=logger,
                observability_service=observability_service,
            )
            ctx.alert_diagnosis_service = alert_diagnosis_service
            ctx.observability_services["alerts"] = alert_diagnosis_service
            ctx.observability_services["diagnosis"] = alert_diagnosis_service
            ctx.runtime_status["observability_alerts"] = alert_diagnosis_service.startup_check()
        except Exception as exc:
            logger.warning("observability alert diagnosis initialization skipped: %s", exc)
            ctx.runtime_status["observability_alerts"] = {"ok": bool(getattr(config, "observability_diagnosis_fail_open", True)), "enabled": bool(getattr(config, "enable_observability_alerts", False) or getattr(config, "enable_observability_diagnosis", False)), "fail_open": True, "error": str(exc)}
        try:
            from wq_workflow.observability.explainability_service import ExplainabilityService

            explainability_service = ExplainabilityService(
                config=config,
                storage=storage,
                db_path=getattr(config, "storage_db_path", "runtime/db/workflow.db"),
                logger=logger,
            )
            ctx.explainability_service = explainability_service
            ctx.observability_services["explainability"] = explainability_service
            ctx.runtime_status["observability_explainability"] = explainability_service.startup_check()
        except Exception as exc:
            logger.warning("observability explainability initialization skipped: %s", exc)
            ctx.runtime_status["observability_explainability"] = {"ok": bool(getattr(config, "observability_explainability_fail_open", True)), "enabled": bool(getattr(config, "enable_run_explainability", False)), "fail_open": True, "mode": "explain_only", "error": str(exc), "auto_action_allowed": False}
    except Exception as exc:
        logger.warning("observability metrics initialization skipped: %s", exc)
        ctx.runtime_status["observability"] = {"ok": bool(getattr(config, "observability_fail_open", True)), "enabled": bool(getattr(config, "enable_observability_metrics", True)), "fail_open": True, "error": str(exc)}
    ctx.monitoring_services["drift_monitor"] = DriftMonitor(storage=storage, config=config, logger=logger)
    ctx.legacy_adapters["orchestrator"] = run_legacy_orchestrator
    if bool(getattr(config, "enable_startup_healthcheck", True)):
        try:
            from wq_workflow.app.healthcheck import run_startup_healthcheck

            ctx.runtime_status["healthcheck"] = run_startup_healthcheck(config, storage=storage, model_registry=model_registry, logger=logger)
        except Exception as exc:
            logger.warning("startup healthcheck skipped: %s", exc)
    return ctx


async def run_async(argv: list[str] | None = None, *, config: Any | None = None) -> int:
    ctx = build_app_context(config=config)
    adapter = ctx.legacy_adapters.get("orchestrator")
    if not getattr(ctx.config, "enable_refactored_pipeline", False):
        return await adapter(ctx, argv=argv)
    from wq_workflow.workflow.pipeline import WorkflowPipeline
    from wq_workflow.workflow.pipeline import has_observe_only_critical_steps, observe_only_critical_step_names

    pipeline = WorkflowPipeline(ctx)
    if has_observe_only_critical_steps(pipeline.steps):
        names = observe_only_critical_step_names(pipeline.steps)
        event = {
            "event": "refactored_pipeline_observe_only_critical_steps",
            "pipeline_mode": "legacy_fallback",
            "official_result_source": "legacy",
            "observe_only_critical_steps": names,
        }
        ctx.runtime_status.setdefault("pipeline_safety_events", []).append(event)
        ctx.runtime_status["pipeline_mode"] = "legacy_fallback"
        ctx.runtime_status["official_result_source"] = "legacy"
        logger = getattr(ctx, "logger", None)
        if not getattr(ctx.config, "allow_observe_only_pipeline", False):
            if logger:
                logger.warning("Refactored pipeline has observe-only critical steps %s; falling back to legacy official run.", names)
            return await adapter(ctx, argv=argv)
        ctx.runtime_status["pipeline_mode"] = "unsafe_observe_only"
        ctx.runtime_status["official_result_source"] = "refactored_unsafe"
        event["pipeline_mode"] = "unsafe_observe_only"
        event["official_result_source"] = "refactored_unsafe"
        if logger:
            logger.warning("UNSAFE: allow_observe_only_pipeline=true; refactored pipeline may not submit/wait/parse real backtests.")
    result = pipeline.run_one_iteration()
    return 0 if result.ok else 1


def run(argv: list[str] | None = None, *, config_path: str | Path | None = None, config: Any | None = None) -> int:
    import asyncio
    return asyncio.run(run_async(argv, config=config))
