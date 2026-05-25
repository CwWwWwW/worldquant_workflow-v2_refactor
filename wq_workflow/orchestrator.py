from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .browser_ops import login
from .browser_supervisor import BrowserSupervisor
from .config import load_config
from .correlation import check_self_correlation, extract_structure
from .core.mutation_constraints import MutationConstraints
from .core.insight import InsightManager
from .core.operator_graph import OperatorGraph
from .core.parser import ExpressionParser, ParseError
from .core.semantic_similarity import SemanticSimilarity
from .core.strategy_engine import StrategyEngine
from .core.structural_mutator import StructuralMutator
from .core.evolution import AlphaSimulator, EvolutionOrchestrator, SidecarContract, suggest_mutation_weights
from .deepseek_client import DeepSeekClient, clean_code
from .dashboard_snapshot import maybe_refresh_dashboard_snapshot
from .fast_expression import refresh_operator_cache_from_platform, validate_fast_expression
from .logging_setup import DISCLAIMER, setup_logging
from .models import SIMULATE_URL, QualityReport, SimulationResult, TemplateFailure, TemplateItem, TemplateSuccess
from .paths import ITERATION_LOG_FIELDS, ITERATION_LOG_FILE, append_csv, ensure_runtime_files, now_ts
from .platform_sc import apply_correlation_quality, sc_payload_from_metrics, strong_feedback_allowed
from .simulate import read_latest_success_for_final_recovery, run_platform_backtest_attempt
from .template_success_detector import RESULT_UNCERTAIN, detect_template_success
from .candidate_pool import CandidatePool
from .templates import split_and_store_templates
from .memory_manager import EvolutionMemory, classify_failure
from .mutation_engine import MutationPlanner, complexity_score, validate_controlled_expression
from .reward_engine import RewardEngine, metric_delta
from .v2_engine import (
    AdaptiveMutationScheduler,
    FamilyEvolutionManager,
    RegimeMutator,
    build_behavior_fingerprint,
    estimate_self_corr,
)


@dataclass
class DsRunMemory:
    forbidden_ops: set[str] = field(default_factory=set)
    recent_error_summaries: list[str] = field(default_factory=list)
    failed_fingerprints: set[str] = field(default_factory=set)

    def remember_platform_error(self, error_text: str, code: str) -> None:
        self.forbidden_ops.update(extract_forbidden_ops(error_text))
        summary = normalize_error_key(error_text)
        if summary:
            self.recent_error_summaries.append(summary[:300])
            self.recent_error_summaries = self.recent_error_summaries[-3:]
        fingerprint = code_fingerprint(code)
        if fingerprint:
            self.failed_fingerprints.add(fingerprint)

    def context(self) -> str:
        parts: list[str] = []
        if self.forbidden_ops:
            parts.append("Forbidden operators in this run: " + ", ".join(sorted(self.forbidden_ops)))
        if self.recent_error_summaries:
            parts.append("Recent platform/local errors:\n" + "\n".join(f"- {item}" for item in self.recent_error_summaries))
        return "\n".join(parts)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="WorldQuant DeepSeek 自动迭代收藏工作流")
    parser.add_argument("--template-file", action="append", default=[], help="包含一个或多个模板和解释的文本文件，可重复传入")
    parser.add_argument("--template-text", default="", help="直接传入模板混合文本")
    parser.add_argument("--max-templates", type=int, default=None, help="覆盖本次最多处理模板数")
    parser.add_argument("--max-iterations", type=int, default=None, help="覆盖单模板最大主循环次数；0 表示不限制")
    parser.add_argument("--split-only", action="store_true", help="只调用 DeepSeek 分割模板并保存，不启动浏览器")
    parser.add_argument("--use-split", action="store_true", help="从 templates/ 已分割模板启动，不重新分割原始文本")
    return parser.parse_args(argv)


async def main(argv: list[str] | None = None, *, experiment_service: Any | None = None, decision_snapshot_service: Any | None = None) -> int:
    args = parse_args(argv)
    ensure_runtime_files()
    setup_logging()
    logging.info(DISCLAIMER.replace("\n", " | "))

    config = load_config()
    if args.max_templates is not None:
        config.max_templates = args.max_templates
    elif not args.use_split and (args.template_file or args.template_text):
        config.max_templates = 0
    if args.max_iterations is not None:
        config.max_iterations_per_template = args.max_iterations
    if experiment_service is None and bool(getattr(config, "enable_experiment_tracking", True)):
        try:
            from .experiment.service import ExperimentService

            experiment_service = ExperimentService(
                config=config,
                db_path=getattr(config, "storage_db_path", "runtime/db/workflow.db"),
                logger=logging.getLogger("wq_workflow.experiment"),
            )
            experiment_service.startup_check()
        except Exception:
            logging.info("Experiment tracking unavailable; continuing legacy workflow", exc_info=True)
            experiment_service = None
    if decision_snapshot_service is None and bool(getattr(config, "enable_decision_snapshots", True)):
        try:
            from .offline.service import DecisionSnapshotService

            decision_snapshot_service = DecisionSnapshotService(
                config=config,
                db_path=getattr(config, "storage_db_path", "runtime/db/workflow.db"),
                logger=logging.getLogger("wq_workflow.offline.decision_snapshot"),
            )
            decision_snapshot_service.startup_check()
        except Exception:
            logging.info("Decision snapshot service unavailable; continuing legacy workflow", exc_info=True)
            decision_snapshot_service = None
    if experiment_service is not None:
        try:
            experiment_service.decision_snapshot_service = decision_snapshot_service
        except Exception:
            pass

    ds = DeepSeekClient(config)
    templates = await split_and_store_templates(
        ds,
        config,
        args.template_file,
        args.template_text,
        use_existing=args.use_split,
    )
    logging.info("本次任务模板数量：%s", len(templates))
    if args.split_only:
        for item in templates:
            print(f"SPLIT_TEMPLATE {item.index}: {item.path}", flush=True)
        logging.info("仅分割模板完成：%s", len(templates))
        return 0

    supervisor = BrowserSupervisor(config)
    successes: list[TemplateSuccess] = []
    failures: list[TemplateFailure] = []
    try:
        await supervisor.start()
        bootstrap_session = await supervisor.new_alpha_session("bootstrap")
        try:
            await login(bootstrap_session.page, bootstrap_session.context, config)
            await refresh_operator_cache_from_platform(bootstrap_session.page)
        finally:
            await supervisor.close_session(bootstrap_session, persist_storage=True)
        for item in templates:
            try:
                success = await process_one_template(supervisor, ds, config, item, experiment_service=experiment_service, decision_snapshot_service=decision_snapshot_service)
                successes.append(success)
                print_success(success)
            except TemplateFailedError as exc:
                failure = exc.failure
                failures.append(failure)
                print_failure(failure)
                logging.warning("模板明确失败，继续下一个：%s reason=%s", item.path, failure.reason)
        logging.info("全部模板已完成并收藏：%s/%s", len(successes), len(templates))
        if failures:
            logging.warning("本次明确失败模板：%s/%s", len(failures), len(templates))
        return 0
    finally:
        await supervisor.close()


def maybe_assign_experiment_candidate(experiment_service: Any | None, candidate_context: dict[str, Any]) -> Any | None:
    if experiment_service is None:
        return None
    try:
        return experiment_service.assign_candidate(candidate_context)
    except Exception:
        logging.info("Experiment assignment skipped", exc_info=True)
        return None


def maybe_record_experiment_result(experiment_service: Any | None, alpha_id: str, result_context: dict[str, Any]) -> Any | None:
    if experiment_service is None:
        return None
    try:
        result = experiment_service.record_result(alpha_id, result_context)
        try:
            experiment_service.update_report()
        except Exception:
            logging.info("Experiment report update skipped", exc_info=True)
        return result
    except Exception:
        logging.info("Experiment result recording skipped", exc_info=True)
        return None


def maybe_record_decision_snapshot(decision_snapshot_service: Any | None, decision_type: str, context: dict[str, Any]) -> Any | None:
    if decision_snapshot_service is None:
        return None
    try:
        return decision_snapshot_service.record_decision(decision_type, context)
    except Exception:
        logging.info("Decision snapshot recording skipped", exc_info=True)
        return None


def maybe_record_decision_outcome(decision_snapshot_service: Any | None, alpha_id: str, outcome_context: dict[str, Any]) -> list[Any]:
    if decision_snapshot_service is None:
        return []
    try:
        return decision_snapshot_service.record_outcome(alpha_id, outcome_context)
    except Exception:
        logging.info("Decision snapshot outcome skipped", exc_info=True)
        return []


async def process_one_template(supervisor: BrowserSupervisor, ds: DeepSeekClient, config, item: TemplateItem, *, experiment_service: Any | None = None, decision_snapshot_service: Any | None = None) -> TemplateSuccess:
    logging.info("开始处理模板：%s file=%s source=%s", item.index, item.path, item.source)
    code, raw = await ds.prepare_alpha(item.code)
    code = ensure_code(code, "DeepSeek 初始优化未返回可用代码")
    alpha_name = f"Auto_Alpha_{item.index:03d}_{now_ts()}"
    iteration = 0
    last_submitted_fingerprint = ""
    automation_retry_count = 0
    automation_retry_total = 0
    last_platform_error_key = ""
    repeated_platform_error_count = 0
    recent_platform_error_codes: list[str] = []
    syntax_error_count = 0
    ds_memory = DsRunMemory()
    evolution_memory = EvolutionMemory()
    mutation_planner = MutationPlanner()
    reward_engine = RewardEngine(
        enable_survival_memory=config.enable_survival_memory,
        enable_pending_reward=config.enable_pending_reward,
        enable_template_governance=config.enable_template_governance,
        enable_exploration_pressure=config.enable_exploration_pressure,
        enable_adaptive_legacy=config.enable_adaptive_legacy,
    )
    candidate_pool = CandidatePool()
    v2_enabled = bool(config.enable_v2_engine)
    behavior_sc_enabled = bool(v2_enabled and config.enable_behavior_sc_pipeline and config.v2_rollout_phase >= 2)
    family_manager = FamilyEvolutionManager()
    adaptive_scheduler = AdaptiveMutationScheduler(phase=config.v2_rollout_phase)
    regime_mutator = RegimeMutator()
    insight_manager = InsightManager() if config.enable_research_insights else None
    sidecar = SidecarContract(
        simulator=AlphaSimulator(
            low_confidence_threshold=float(getattr(config, "simulator_low_confidence_threshold", 0.2))
        ),
        enabled=bool(getattr(config, "enable_sidecar_evolution", False)),
        config=config,
    )
    evolution_orchestrator = EvolutionOrchestrator(config)
    evolution_orchestrator.bootstrap(candidate_pool, evolution_memory)
    pending_mutation: dict[str, object] | None = None
    skipped_expression_fingerprints: set[str] = set()
    consecutive_simulator_skips = 0
    simulator_skip_disabled_for_template = False
    max_syntax_errors = config.max_iterations_per_template if config.max_iterations_per_template and config.max_iterations_per_template > 0 else 12
    max_iterations = config.max_iterations_per_template if config.max_iterations_per_template and config.max_iterations_per_template > 0 else 0
    no_progress_key = ""
    no_progress_count = 0
    no_progress_limit = 8
    automation_retry_total_limit = 9
    result_uncertain_count = 0
    last_result: SimulationResult | None = None
    last_result_code = ""
    maybe_refresh_dashboard_snapshot(force=True)

    while max_iterations == 0 or iteration < max_iterations:
        iteration += 1
        maybe_refresh_dashboard_snapshot()
        placeholder_error = invalid_placeholder_reason(code)
        if placeholder_error:
            no_progress_key, no_progress_count = track_no_progress(
                item,
                alpha_name,
                iteration,
                code,
                f"placeholder:{normalize_error_key(placeholder_error)}",
                no_progress_key,
                no_progress_count,
                no_progress_limit,
            )
            syntax_error_count += 1
            fail_if_syntax_exhausted(item, alpha_name, code, placeholder_error, syntax_error_count, max_syntax_errors)
            logging.warning("检测到不可提交占位符，先交给 DeepSeek 修复：%s", placeholder_error)
            ds_memory.remember_platform_error(placeholder_error, code)
            evolution_memory.save_failure_pattern(
                error_type=classify_failure(placeholder_error),
                expression=code,
                root_cause=placeholder_error,
            )
            placeholder_plan = mutation_planner.plan({}, code, placeholder_error)
            placeholder_context = build_mutation_context(
                code,
                {},
                placeholder_plan,
                evolution_memory,
                candidate_pool=candidate_pool,
                v2_enabled=v2_enabled,
                behavior_sc_enabled=behavior_sc_enabled,
                scheduler=adaptive_scheduler,
                template_controller=reward_engine.template_controller,
                enable_exploration_pressure=config.enable_exploration_pressure,
                insight_manager=insight_manager,
                insight_top_k=config.insight_top_k,
            )
            code, raw = await ds.repair_platform_error(code, with_ds_memory(placeholder_error, ds_memory), "", placeholder_context)
            code = ensure_code(code, "DeepSeek 占位符修复未返回代码")
            log_iteration(item, alpha_name, iteration, "placeholder_repair", code, placeholder_error, None, {}, raw, "")
            continue

        syntax_error = validate_fast_expression(code, enable_v2_engine=v2_enabled)
        if syntax_error:
            no_progress_key, no_progress_count = track_no_progress(
                item,
                alpha_name,
                iteration,
                code,
                f"syntax:{normalize_error_key(syntax_error)}",
                no_progress_key,
                no_progress_count,
                no_progress_limit,
            )
            syntax_error_count += 1
            fail_if_syntax_exhausted(item, alpha_name, code, syntax_error, syntax_error_count, max_syntax_errors)
            logging.warning("本地 Fast Expression 预检阻断，交给 DeepSeek 修复：%s", syntax_error)
            ds_memory.remember_platform_error(syntax_error, code)
            evolution_memory.save_failure_pattern(
                error_type=classify_failure(syntax_error),
                expression=code,
                root_cause=syntax_error,
            )
            syntax_plan = mutation_planner.plan({}, code, syntax_error)
            syntax_context = build_mutation_context(
                code,
                {},
                syntax_plan,
                evolution_memory,
                candidate_pool=candidate_pool,
                v2_enabled=v2_enabled,
                behavior_sc_enabled=behavior_sc_enabled,
                scheduler=adaptive_scheduler,
                template_controller=reward_engine.template_controller,
                enable_exploration_pressure=config.enable_exploration_pressure,
                insight_manager=insight_manager,
                insight_top_k=config.insight_top_k,
            )
            code, raw = await ds.repair_platform_error(code, with_ds_memory(syntax_error, ds_memory), "", syntax_context)
            code = ensure_code(code, "DeepSeek 本地语法预检修复未返回代码")
            log_iteration(item, alpha_name, iteration, "local_syntax_repair", code, syntax_error, None, {}, raw, "")
            continue

        structure = extract_structure(code)
        correlation = check_self_correlation(
            code,
            structure,
            metrics={},
            enable_v2_engine=v2_enabled,
            enable_behavior_sc_pipeline=behavior_sc_enabled,
        )
        if not correlation.passed:
            logging.warning("迭代前自相关红线阻断，交给 DeepSeek 差异化：%s", correlation.reason)
            local_v2_candidate = generate_local_v2_candidate(
                code,
                {},
                mutation_planner.plan({}, code, correlation.reason),
                candidate_pool,
                evolution_memory,
                adaptive_scheduler,
                regime_mutator,
                v2_enabled=v2_enabled,
                behavior_sc_enabled=behavior_sc_enabled,
                template_controller=reward_engine.template_controller,
                enable_exploration_pressure=config.enable_exploration_pressure,
            )
            if local_v2_candidate:
                code = str(local_v2_candidate["expression"])
                raw = json.dumps({"source": "local_v2_correlation_repair", **local_v2_candidate}, ensure_ascii=False)
                log_iteration(item, alpha_name, iteration, "v2_correlation_repair", code, "", None, {}, raw, "")
            else:
                code, raw = await ds.avoid_correlation(code, correlation.reason)
                code = ensure_code(code, "DeepSeek 自相关差异化未返回代码")
                log_iteration(item, alpha_name, iteration, "correlation_repair", code, "", None, {}, raw, "")
            continue

        logging.info("模板 %s 第 %s 次平台回测：%s", item.index, iteration, alpha_name)
        current_fingerprint = code_fingerprint(code)
        if should_block_repeated_simulator_skip(code, skipped_expression_fingerprints):
            logging.info("EVOLUTION_SIMULATOR_SKIP_DUPLICATE_REGENERATE alpha=%s fingerprint=%s", alpha_name, current_fingerprint)
            code, raw = await ds.avoid_correlation(
                code,
                "This candidate was already skipped by the GA/RL simulator in this template; generate a materially different candidate.",
            )
            code = ensure_code(code, "DeepSeek simulator-skip regeneration returned no code")
            log_iteration(item, alpha_name, iteration, "evolution_simulator_regenerate", code, "", None, {}, raw, "")
            pending_mutation = None
            continue
        if current_fingerprint == last_submitted_fingerprint:
            logging.warning("检测到与上一轮完全相同的因子，先交给 DeepSeek 做轻微调整，避免平台阻止连续相同回测")
            code, raw = await ds.avoid_correlation(code, "平台会阻止相同因子连续回测；请只轻微调整窗口、分桶或中性化层级，保留核心逻辑")
            code = ensure_code(code, "DeepSeek 连续相同因子调整未返回代码")
            log_iteration(item, alpha_name, iteration, "duplicate_consecutive_repair", code, "", None, {}, raw, "")
            continue
        maybe_record_sidecar_pre_backtest(
            sidecar,
            config,
            alpha_name=alpha_name,
            code=code,
            metrics={},
            candidate_pool=candidate_pool,
            evolution_memory=evolution_memory,
        )
        candidate_source = str((pending_mutation or {}).get("candidate_source") or ("mutation" if pending_mutation else "seed"))
        is_pending_candidate = bool((pending_mutation or {}).get("is_pending_candidate", bool(pending_mutation)))
        if simulator_skip_disabled_for_template:
            candidate_source = "current_code" if not pending_mutation else candidate_source
        alpha_id = f"{alpha_name}:{iteration}"
        skip_backtest, simulator_observation = evolution_orchestrator.before_backtest(
            {
                "alpha_id": alpha_id,
                "expression": code,
                "metrics": {},
                "parent_reward": float((pending_mutation or {}).get("parent_reward") or 0.0),
                "mutation_type": str((pending_mutation or {}).get("mutation_type") or ""),
                "candidate_source": candidate_source,
                "is_pending_candidate": is_pending_candidate and not simulator_skip_disabled_for_template,
                "parent_ids": (pending_mutation or {}).get("parent_ids") or [],
                "policy_weights": (pending_mutation or {}).get("policy_weights") or {},
            },
            dict((pending_mutation or {}).get("mutation_context") or {}),
        )
        if skip_backtest:
            logging.info("EVOLUTION_SIMULATOR_SKIP alpha=%s observation=%s", alpha_name, simulator_observation)
            log_iteration(item, alpha_name, iteration, "evolution_simulator_skip", code, "", None, {}, json.dumps(simulator_observation, ensure_ascii=False), "")
            remember_simulator_skip(code, skipped_expression_fingerprints)
            consecutive_simulator_skips += 1
            pending_mutation = None
            last_submitted_fingerprint = current_fingerprint
            if consecutive_simulator_skips >= int(getattr(config, "simulator_max_consecutive_skips_per_template", 3) or 3):
                simulator_skip_disabled_for_template = True
                logging.info("EVOLUTION_SIMULATOR_SKIP_LIMIT_REACHED alpha=%s limit=%s", alpha_name, consecutive_simulator_skips)
            continue
        consecutive_simulator_skips = 0
        candidate_context = {
            "alpha_id": alpha_id,
            "expression": code,
            "template_name": item.path or item.source,
            "template_family": item.source or item.path,
            "mutation_type": str((pending_mutation or {}).get("mutation_type") or candidate_source),
            "candidate_source": candidate_source,
            "behavior_family": str((pending_mutation or {}).get("behavior_family") or ""),
            "raw_pending_mutation": pending_mutation or {},
        }
        assignment = maybe_assign_experiment_candidate(experiment_service, candidate_context)
        maybe_record_decision_snapshot(
            decision_snapshot_service,
            "candidate_acceptance",
            {
                **candidate_context,
                "experiment_id": getattr(assignment, "experiment_id", None),
                "arm_id": getattr(assignment, "arm_id", None),
                "chosen_action": {"action_id": "submit_backtest", "action_type": "candidate_acceptance", "name": "submit_backtest", "source": "legacy"},
                "legacy_choice": {"action_id": "submit_backtest", "action_type": "candidate_acceptance", "name": "submit_backtest", "source": "legacy"},
                "available_actions": [
                    {"action_id": "submit_backtest", "action_type": "candidate_acceptance", "name": "submit_backtest", "source": "legacy"},
                    {"action_id": "skip_candidate", "action_type": "candidate_acceptance", "name": "skip_candidate", "source": "unknown"},
                ],
                "context": candidate_context,
                "raw_payload": {"experiment_assignment": assignment.to_dict() if hasattr(assignment, "to_dict") else None, "tracking_only": True},
            },
        )
        result = await run_platform_backtest_attempt(
            supervisor,
            code=code,
            alpha_name=alpha_name,
            config=config,
            template_file=item.path,
        )
        maybe_record_sidecar_post_backtest(sidecar, config, alpha_name=alpha_name, code=code, result=result)
        last_submitted_fingerprint = current_fingerprint
        last_result = result
        last_result_code = code

        if result.error:
            if is_result_uncertain_result(result):
                result_uncertain_count += 1
                logging.warning(
                    "%s after platform polling, retrying same code without failure feedback: count=%s error=%s",
                    RESULT_UNCERTAIN,
                    result_uncertain_count,
                    result.error.text,
                )
                log_iteration(item, alpha_name, iteration, "result_uncertain", code, result.error.text, None, {}, "", result.screenshot)
                if result_uncertain_count >= automation_retry_total_limit:
                    fail_current_template(
                        item,
                        alpha_name,
                        code,
                        f"result visibility remained uncertain after {result_uncertain_count} retries: {result.error.text}",
                        iteration,
                        result.screenshot,
                    )
                last_submitted_fingerprint = ""
                await asyncio.sleep(min(30, 3 * result_uncertain_count))
                continue
            if is_automation_error(result.error.text):
                automation_retry_count += 1
                automation_retry_total += 1
                if automation_retry_total >= automation_retry_total_limit:
                    fail_current_template(
                        item,
                        alpha_name,
                        code,
                        f"automation retry budget exhausted after {automation_retry_total} attempts: {result.error.text}",
                        iteration,
                        result.screenshot,
                    )
                logging.warning(
                    "网页自动化未触发真实新回测，FSM recovery 后重试当前代码：attempt=%s recovery=%s error=%s",
                    automation_retry_count,
                    result.recovery_level,
                    result.error.text,
                )
                log_iteration(item, alpha_name, iteration, "automation_retry", code, result.error.text, None, {}, "", result.screenshot)
                await asyncio.sleep(min(30, 2 * automation_retry_count))
                if automation_retry_count >= 3:
                    logging.warning("连续 %s 次未触发真实新回测，执行页面硬恢复后继续 workflow", automation_retry_count)
                    recovery_session = await supervisor.new_alpha_session(f"{alpha_name}_hard_recovery")
                    try:
                        await recovery_session.page.goto(
                            SIMULATE_URL,
                            wait_until="domcontentloaded",
                            timeout=60000,
                        )
                        await asyncio.sleep(8)
                    finally:
                        await supervisor.close_session(recovery_session, persist_storage=False)
                    automation_retry_count = 0
                    last_submitted_fingerprint = ""
                    continue
                last_submitted_fingerprint = ""
                continue
            automation_retry_count = 0
            platform_error_key = normalize_error_key(result.error.text)
            failure_context = {
                "success": False,
                "reward": -0.5,
                "metrics": result.metrics if isinstance(result.metrics, dict) else {},
                "quality_passed": False,
                "platform_sc": result.platform_sc if isinstance(result.platform_sc, dict) else {},
                "platform_sc_status": (result.platform_sc or {}).get("status") if isinstance(result.platform_sc, dict) else None,
                "platform_sc_abs_max": (result.platform_sc or {}).get("abs_max") if isinstance(result.platform_sc, dict) else None,
                "failure_type": classify_failure(result.error.text),
                "failure_reason": result.error.text,
            }
            maybe_record_experiment_result(experiment_service, alpha_id, failure_context)
            maybe_record_decision_outcome(decision_snapshot_service, alpha_id, failure_context)
            if is_syntax_error_text(result.error.text):
                syntax_error_count += 1
                fail_if_syntax_exhausted(item, alpha_name, code, result.error.text, syntax_error_count, max_syntax_errors, result.screenshot)
            if platform_error_key and platform_error_key == last_platform_error_key:
                repeated_platform_error_count += 1
            else:
                repeated_platform_error_count = 1
                last_platform_error_key = platform_error_key
                recent_platform_error_codes = []
            no_progress_key, no_progress_count = track_no_progress(
                item,
                alpha_name,
                iteration,
                code,
                f"platform:{platform_error_key}",
                no_progress_key,
                no_progress_count,
                no_progress_limit,
                result.screenshot,
            )
            recent_platform_error_codes.append(code)
            recent_platform_error_codes = recent_platform_error_codes[-3:]
            ds_memory.remember_platform_error(result.error.text, code)
            evolution_memory.save_failure_pattern(
                error_type=classify_failure(result.error.text),
                expression=code,
                root_cause=result.error.text,
            )
            if pending_mutation:
                before_metrics = pending_mutation.get("metrics_before") if isinstance(pending_mutation.get("metrics_before"), dict) else {}
                expression_before = str(pending_mutation.get("expression_before") or "")
                evolution_memory.save_mutation(
                    alpha_id=f"{alpha_name}:{iteration}:error",
                    parent_id=str(pending_mutation.get("parent_id") or alpha_name),
                    expression_before=expression_before,
                    expression_after=code,
                    mutation_type=str(pending_mutation.get("mutation_type") or "unknown"),
                    metrics_before=before_metrics,
                    metrics_after={},
                    delta=metric_delta(before_metrics, {}),
                    passed=False,
                    reward=-0.5,
                    quality_passed=False,
                    failure_reason=result.error.text,
                    complexity_before=complexity_score(expression_before),
                    complexity_after=complexity_score(code),
                )
                pending_mutation = None

            logging.warning(
                "平台返回代码错误，交给 DeepSeek 修复：repeat=%s error=%s",
                repeated_platform_error_count,
                result.error.text,
            )
            repair_error_text = build_repair_error_context(
                result.error.text,
                repeated_platform_error_count,
                recent_platform_error_codes,
            )
            repair_error_text = with_ds_memory(repair_error_text, ds_memory)
            repair_plan = mutation_planner.plan({}, code, repair_error_text)
            repair_context = build_mutation_context(
                code,
                {},
                repair_plan,
                evolution_memory,
                candidate_pool=candidate_pool,
                v2_enabled=v2_enabled,
                behavior_sc_enabled=behavior_sc_enabled,
                scheduler=adaptive_scheduler,
                template_controller=reward_engine.template_controller,
                enable_exploration_pressure=config.enable_exploration_pressure,
                insight_manager=insight_manager,
                insight_top_k=config.insight_top_k,
            )
            code, raw = await ds.repair_platform_error(code, repair_error_text, result.error.page_text, repair_context)
            code = ensure_code(code, "DeepSeek 平台错误修复未返回代码")
            log_iteration(item, alpha_name, iteration, "platform_error_repair", code, result.error.text, None, {}, raw, result.screenshot)
            continue

        automation_retry_count = 0
        automation_retry_total = 0
        no_progress_key = ""
        no_progress_count = 0
        syntax_error_count = 0
        repeated_platform_error_count = 0
        last_platform_error_key = ""
        recent_platform_error_codes = []
        quality = result.quality or QualityReport(False, "unknown")
        if is_result_uncertain_result(result):
            result_uncertain_count += 1
            logging.info(
                "%s visible result is not stable enough for reward/migration feedback: count=%s reason=%s",
                RESULT_UNCERTAIN,
                result_uncertain_count,
                result.template_success_reason or "empty_or_delayed_result",
            )
            log_iteration(
                item,
                alpha_name,
                iteration,
                "result_uncertain",
                code,
                result.template_success_reason or "empty_or_delayed_result",
                quality,
                result.metrics,
                "",
                result.screenshot,
                platform_sc=result.platform_sc,
            )
            if result_uncertain_count >= automation_retry_total_limit:
                fail_current_template(
                    item,
                    alpha_name,
                    code,
                    f"result visibility remained uncertain after {result_uncertain_count} retries",
                    iteration,
                    result.screenshot,
                )
            last_submitted_fingerprint = ""
            await asyncio.sleep(min(30, 3 * result_uncertain_count))
            continue
        result_uncertain_count = 0
        mutation_reward = record_pending_mutation_result(
            pending=pending_mutation,
            alpha_name=alpha_name,
            iteration=iteration,
            code=code,
            metrics=result.metrics,
            quality=quality,
            template_success=result.template_success,
            template_success_reason=result.template_success_reason,
            reward_engine=reward_engine,
            evolution_memory=evolution_memory,
            candidate_pool=candidate_pool,
            v2_enabled=v2_enabled,
            behavior_sc_enabled=behavior_sc_enabled,
            family_manager=family_manager,
            platform_sc=result.platform_sc,
        )
        try:
            evolution_candidate_source = str(candidate_source or "initial_or_untracked")
            evolution_mutation_type = "initial_or_untracked"
            evolution_parent_ids: list[object] = []
            evolution_parent_reward = 0.0
            evolution_is_pending = False
            evolution_context: dict[str, object] = {}
            evolution_behavior_family = "unknown"
            evolution_estimated_self_corr = None
            evolution_lineage_depth = 0
            evolution_failure_reason = ""
            if pending_mutation:
                evolution_candidate_source = str(
                    pending_mutation.get("candidate_source") or pending_mutation.get("source") or "mutation"
                )
                evolution_mutation_type = str(
                    pending_mutation.get("mutation_type") or pending_mutation.get("type") or "unknown"
                )
                raw_parent_ids = pending_mutation.get("parent_ids") or [pending_mutation.get("parent_id")]
                evolution_parent_ids = [parent for parent in raw_parent_ids if parent] if isinstance(raw_parent_ids, list) else [raw_parent_ids]
                try:
                    evolution_parent_reward = float(pending_mutation.get("parent_reward", 0.0) or 0.0)
                except (TypeError, ValueError):
                    evolution_parent_reward = 0.0
                evolution_is_pending = bool(pending_mutation.get("is_pending_candidate", True))
                evolution_context = dict(pending_mutation.get("mutation_context") or {})
                evolution_behavior_family = str(pending_mutation.get("behavior_family") or "unknown")
                evolution_estimated_self_corr = pending_mutation.get("estimated_self_corr", None)
                try:
                    evolution_lineage_depth = int(pending_mutation.get("lineage_depth") or 0)
                except (TypeError, ValueError):
                    evolution_lineage_depth = 0
                evolution_failure_reason = str(pending_mutation.get("failure_reason") or "")
            elif simulator_skip_disabled_for_template:
                evolution_candidate_source = "current_code"
            evolution_orchestrator.after_backtest(
                candidate={
                    "alpha_id": alpha_id,
                    "expression": code,
                    "metrics": result.metrics if isinstance(result.metrics, dict) else {},
                    "parent_ids": evolution_parent_ids,
                    "mutation_type": evolution_mutation_type,
                    "parent_reward": evolution_parent_reward,
                    "behavior_family": evolution_behavior_family,
                    "estimated_self_corr": evolution_estimated_self_corr,
                    **sc_payload_from_metrics(result.metrics if isinstance(result.metrics, dict) else {}, result.platform_sc),
                    "lineage_depth": evolution_lineage_depth,
                    "failure_reason": evolution_failure_reason,
                    "failure_type": classify_failure(evolution_failure_reason) if evolution_failure_reason else "",
                    "candidate_source": evolution_candidate_source,
                    "is_pending_candidate": evolution_is_pending,
                    "simulator_observation": simulator_observation or {},
                },
                result=result,
                reward_payload={
                    "reward": mutation_reward,
                    "passed": bool(quality.passed),
                    "success": bool(quality.passed or result.template_success),
                    "template_success": bool(result.template_success),
                    "metrics": result.metrics if isinstance(result.metrics, dict) else {},
                    **sc_payload_from_metrics(result.metrics if isinstance(result.metrics, dict) else {}, result.platform_sc),
                },
                context=evolution_context,
            )
        except Exception:
            logging.info("Evolution after_backtest call skipped", exc_info=True)
        outcome_context = {
            "success": bool(quality.passed or result.template_success),
            "reward": mutation_reward,
            "metrics": result.metrics if isinstance(result.metrics, dict) else {},
            "quality": quality.to_dict() if hasattr(quality, "to_dict") else {},
            "quality_passed": bool(quality.passed),
            "platform_sc": result.platform_sc if isinstance(result.platform_sc, dict) else {},
            "platform_sc_status": (result.platform_sc or {}).get("status") if isinstance(result.platform_sc, dict) else None,
            "platform_sc_abs_max": (result.platform_sc or {}).get("abs_max") if isinstance(result.platform_sc, dict) else None,
            "failure_type": "" if bool(quality.passed or result.template_success) else "quality_failed",
        }
        maybe_record_experiment_result(experiment_service, alpha_id, outcome_context)
        maybe_record_decision_outcome(decision_snapshot_service, alpha_id, outcome_context)
        await maybe_distill_research_insights(insight_manager, ds, config)
        maybe_refresh_dashboard_snapshot(force=True)
        if pending_mutation:
            logging.info(
                "Evolution mutation recorded: type=%s reward=%s",
                pending_mutation.get("mutation_type"),
                mutation_reward,
            )
            pending_mutation = None
        log_iteration(
            item,
            alpha_name,
            iteration,
            "platform_result",
            code,
            "",
            quality,
            result.metrics,
            "",
            result.screenshot,
            platform_sc=result.platform_sc,
        )

        if quality.passed or result.template_success:
            return TemplateSuccess(
                item.path,
                alpha_name,
                code,
                result.metrics,
                quality,
                result.screenshot,
                template_success=result.template_success,
                template_success_reason=result.template_success_reason,
            )

        logging.info("平台质量未达标，按 IS Summary / IS Testing Status 交给 DeepSeek 迭代")
        parent_candidate = candidate_pool.select_next_parent()
        fallback_parent = parent_candidate or {
            "alpha_id": alpha_name,
            "expression": code,
            "metrics": result.metrics,
            "reward": mutation_reward,
        }
        parent_a, parent_b = evolution_orchestrator.choose_parents(fallback_parent)
        parent_candidate = parent_a or fallback_parent
        parent_code = str(parent_candidate.get("expression") or code)
        parent_metrics = parent_candidate.get("metrics") if isinstance(parent_candidate.get("metrics"), dict) else result.metrics
        failure_reason = quality_failure_reason(quality, result.metrics)
        no_progress_key, no_progress_count = track_no_progress(
            item,
            alpha_name,
            iteration,
            code,
            f"quality:{normalize_error_key(failure_reason)}",
            no_progress_key,
            no_progress_count,
            no_progress_limit,
            result.screenshot,
        )
        mutation_weights_hint = (
            suggest_mutation_weights(evolution_memory.load_recent_history(limit=200))
            if bool(getattr(config, "enable_sidecar_evolution", False))
            and bool(getattr(config, "enable_evolution_policy", False))
            else {}
        )
        mutation_plan = mutation_planner.plan(
            parent_metrics,
            parent_code,
            failure_reason,
            weight_hint=mutation_weights_hint,
            enable_evolution_policy=bool(getattr(config, "enable_evolution_policy", False)),
        )
        mutation_context = build_mutation_context(
            parent_code,
            parent_metrics,
            mutation_plan,
            evolution_memory,
            candidate_pool=candidate_pool,
            v2_enabled=v2_enabled,
            behavior_sc_enabled=behavior_sc_enabled,
            scheduler=adaptive_scheduler,
            template_controller=reward_engine.template_controller,
            enable_exploration_pressure=config.enable_exploration_pressure,
            insight_manager=insight_manager,
            insight_top_k=config.insight_top_k,
        )
        selected_mutation, policy_weights = evolution_orchestrator.choose_mutation(
            list(getattr(mutation_plan, "allowed_mutations", []) or []),
            mutation_context,
        )
        if selected_mutation:
            mutation_context["selected_mutation"] = selected_mutation
            mutation_context["policy_weights"] = policy_weights
            if selected_mutation in mutation_plan.allowed_mutations:
                mutation_plan.allowed_mutations = [selected_mutation] + [
                    item for item in mutation_plan.allowed_mutations if item != selected_mutation
                ]
                mutation_plan.priority = selected_mutation
        previous_code = parent_code
        crossover_candidate = evolution_orchestrator.maybe_make_crossover_candidate(parent_candidate, parent_b, mutation_context)
        local_candidate = crossover_candidate or generate_local_v2_candidate(
            parent_code,
            parent_metrics,
            mutation_plan,
            candidate_pool,
            evolution_memory,
            adaptive_scheduler,
            regime_mutator,
            v2_enabled=v2_enabled,
            behavior_sc_enabled=behavior_sc_enabled,
            template_controller=reward_engine.template_controller,
            enable_exploration_pressure=config.enable_exploration_pressure,
        )
        if not local_candidate:
            local_candidate = generate_local_structural_candidate(
                parent_code,
                parent_metrics,
                mutation_plan,
                candidate_pool,
                evolution_memory,
                enable_v2_engine=v2_enabled,
            )
        if local_candidate:
            code = str(local_candidate["expression"])
            raw = json.dumps(
                {
                    "source": local_candidate.get("source", "local_structural_mutator"),
                    "mutation_type": local_candidate.get("mutation_type", ""),
                    "description": local_candidate.get("description", ""),
                    "similarity": local_candidate.get("similarity", ""),
                },
                ensure_ascii=False,
            )
        else:
            code, raw = await ds.improve_quality(parent_code, quality, result.page_text, mutation_context)
            code = ensure_code(code, "DeepSeek 质量迭代未返回代码")
        controlled_error = validate_controlled_expression(parent_code, code, mutation_plan, enable_v2_engine=v2_enabled)
        if controlled_error:
            evolution_memory.save_failure_pattern(
                error_type=classify_failure(controlled_error),
                expression=code,
                root_cause=controlled_error,
            )
            code, raw = await ds.repair_platform_error(code, controlled_error, "", mutation_context)
            code = ensure_code(code, "DeepSeek controlled mutation repair returned no code")
            controlled_error = validate_controlled_expression(parent_code, code, mutation_plan, enable_v2_engine=v2_enabled)
            if controlled_error:
                evolution_memory.save_failure_pattern(
                    error_type=classify_failure(controlled_error),
                    expression=code,
                    root_cause=controlled_error,
                )
                log_iteration(
                    item,
                    alpha_name,
                    iteration,
                    "controlled_mutation_rejected",
                    code,
                    controlled_error,
                    quality,
                    result.metrics,
                    raw,
                    result.screenshot,
                )
                code = parent_code
                await asyncio.sleep(0)
                continue
        if code_fingerprint(code) == code_fingerprint(previous_code):
            logging.warning("DeepSeek 质量迭代返回代码与上一轮相同，要求其基于同一结果做实质调整")
            code, raw = await ds.avoid_correlation(code, "质量未达标且上一轮 DeepSeek 返回代码未发生变化；请保留核心逻辑但必须实质调整窗口、平滑、rank 或中性化结构")
            code = ensure_code(code, "DeepSeek 二次质量调整未返回代码")
        pending_mutation = {
            "parent_id": str(parent_candidate.get("alpha_id")) if parent_candidate else alpha_name,
            "parent_ids": local_candidate.get("parent_ids") if local_candidate and isinstance(local_candidate.get("parent_ids"), list) else [str(parent_candidate.get("alpha_id")) if parent_candidate else alpha_name],
            "parent_reward": float((parent_candidate or {}).get("reward") or 0.0),
            "expression_before": parent_code,
            "metrics_before": parent_metrics,
            "mutation_type": str(local_candidate.get("mutation_type")) if local_candidate else mutation_plan.primary_mutation(),
            "failure_reason": failure_reason,
            "mutation_context": mutation_context,
            "candidate_source": str(local_candidate.get("candidate_source") or local_candidate.get("source") or "local_v2") if local_candidate else "deepseek_rewrite",
            "is_pending_candidate": True,
            "policy_weights": policy_weights,
        }
        if v2_enabled:
            parent_family = str((parent_candidate or {}).get("behavior_family") or build_behavior_fingerprint(parent_code).get("family") or "legacy")
            child_fingerprint = build_behavior_fingerprint(code)
            child_family = str(child_fingerprint.get("family") or "legacy")
            estimate = estimate_self_corr(code, candidate_pool._read(), metrics=parent_metrics)
            pending_mutation.update(
                {
                    "behavior_family": child_family,
                    "behavior_fingerprint": child_fingerprint,
                    "estimated_self_corr": estimate.get("estimated_self_corr", 0.0),
                    "family_reward_inheritance": family_manager.inheritance_metadata(
                        parent_family=parent_family,
                        child_family=child_family,
                        parent_reward=float((parent_candidate or {}).get("reward") or 0.0),
                    ),
                    "lineage_depth": int((parent_candidate or {}).get("lineage_depth") or 0) + 1,
                }
            )
        log_iteration(item, alpha_name, iteration, "quality_repair", code, "", quality, result.metrics, raw, result.screenshot)
        await asyncio.sleep(0)

    recovered = recover_success_from_cached_result(item, alpha_name, last_result, last_result_code, config)
    if recovered:
        return recovered
    latest_recovered = await read_latest_success_for_final_recovery(
        supervisor,
        alpha_name=alpha_name,
        code=last_result_code or code,
        config=config,
        template_file=item.path,
    )
    if latest_recovered and (latest_recovered.template_success or (latest_recovered.quality and latest_recovered.quality.passed)):
        return template_success_from_result(item, latest_recovered, latest_recovered.code or last_result_code or code)

    failure = TemplateFailure(
        template_file=item.path,
        alpha_name=alpha_name,
        code=code,
        reason=f"单模板主循环达到上限 {max_iterations} 次，停止该模板",
    )
    log_iteration(item, alpha_name, iteration, "template_failed", code, failure.reason, None, {}, "", "")
    raise TemplateFailedError(failure)


def recover_success_from_cached_result(
    item: TemplateItem,
    alpha_name: str,
    result: SimulationResult | None,
    code: str,
    config,
) -> TemplateSuccess | None:
    if not result:
        return None
    if result.template_success or (result.quality and result.quality.passed):
        logging.info("Recovered success from cached result before max_loop failure")
        return template_success_from_result(item, result, code or result.code)
    if not result.page_text:
        return None
    detection = detect_template_success(
        result.page_text,
        show_test_period_revealed=True,
        thresholds=config.thresholds,
        expression=code or result.code,
    )
    if not detection.template_success:
        return None
    logging.info("Recovered confirmed success from cached page_text before max_loop failure: %s", detection.reason)
    quality = result.quality or QualityReport(False, "unknown")
    return TemplateSuccess(
        item.path,
        alpha_name,
        code or result.code,
        result.metrics,
        quality,
        result.screenshot,
        template_success=True,
        template_success_reason=detection.reason,
    )


def template_success_from_result(item: TemplateItem, result: SimulationResult, code: str) -> TemplateSuccess:
    return TemplateSuccess(
        item.path,
        result.alpha_name,
        code,
        result.metrics,
        result.quality or QualityReport(False, "unknown"),
        result.screenshot,
        template_success=result.template_success,
        template_success_reason=result.template_success_reason,
    )


class TemplateFailedError(RuntimeError):
    def __init__(self, failure: TemplateFailure) -> None:
        super().__init__(failure.reason)
        self.failure = failure


def fail_current_template(
    item: TemplateItem,
    alpha_name: str,
    code: str,
    reason: str,
    iteration: int,
    screenshot: str = "",
) -> None:
    failure = TemplateFailure(
        template_file=item.path,
        alpha_name=alpha_name,
        code=code,
        reason=reason,
        screenshot=screenshot,
    )
    log_iteration(item, alpha_name, iteration, "template_failed", code, failure.reason, None, {}, "", screenshot)
    raise TemplateFailedError(failure)


def track_no_progress(
    item: TemplateItem,
    alpha_name: str,
    iteration: int,
    code: str,
    reason_key: str,
    previous_key: str,
    previous_count: int,
    limit: int,
    screenshot: str = "",
) -> tuple[str, int]:
    key = f"{reason_key}|{code_fingerprint(code)}"
    count = previous_count + 1 if key == previous_key else 1
    if count >= limit:
        fail_current_template(
            item,
            alpha_name,
            code,
            f"no-progress circuit breaker tripped after {count} repeated attempts: {reason_key}",
            iteration,
            screenshot,
        )
    return key, count


def ensure_code(code: str, message: str) -> str:
    cleaned = clean_code(code)
    if not cleaned:
        raise RuntimeError(message)
    return cleaned


def code_fingerprint(code: str) -> str:
    return re.sub(r"\s+", "", clean_code(code).lower())


def simulator_skip_key(expression: str) -> str:
    return code_fingerprint(expression)


def should_block_repeated_simulator_skip(expression: str, skipped_fingerprints: set[str]) -> bool:
    key = simulator_skip_key(expression)
    return bool(key and key in skipped_fingerprints)


def remember_simulator_skip(expression: str, skipped_fingerprints: set[str]) -> str:
    key = simulator_skip_key(expression)
    if key:
        skipped_fingerprints.add(key)
    return key


def is_automation_error(text: str) -> bool:
    value = text or ""
    return "[AUTOMATION]" in value and "[FINAL_CORRELATION]" not in value


def is_result_uncertain_result(result: SimulationResult) -> bool:
    if result.template_success or (result.quality and result.quality.passed):
        return False
    if result.result_uncertain or result.success_candidate:
        return True
    text = result.error.text if result.error else ""
    if text and re.search(r"\[AUTOMATION_TIMEOUT\]|quality_parse_missing|empty payload|temporar(?:y|ily)|latency|not visible|still loading", text, re.I):
        return True
    if result.ok and not (result.page_text or "").strip():
        return True
    if result.ok and result.quality:
        has_status_counts = bool(result.quality.pass_count or result.quality.fail_count or result.quality.pending_count)
        if result.quality.status == "unknown" and not result.metrics and not has_status_counts:
            return True
    return False


def normalize_error_key(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def extract_forbidden_ops(text: str) -> set[str]:
    found: set[str] = set()
    for pattern in [
        r'unknown operator\s+"([^"]+)"',
        r'inaccessible or unknown operator\s+"([^"]+)"',
        r"unknown operator\s+'([^']+)'",
        r"不可用算子[:：]\s*([A-Za-z_][A-Za-z0-9_]*)",
    ]:
        for match in re.finditer(pattern, text or "", re.I):
            found.add(match.group(1).lower())
    return found


def with_ds_memory(error_text: str, memory: DsRunMemory) -> str:
    context = memory.context()
    if not context:
        return error_text
    return (
        f"{error_text}\n\n"
        "Run memory for DeepSeek repair:\n"
        f"{context}\n"
        "Do not reuse any forbidden operator or recently failed structure."
    )


def build_repair_error_context(error_text: str, repeat_count: int, recent_codes: list[str]) -> str:
    if repeat_count <= 1:
        return error_text
    code_blocks = []
    for index, failed_code in enumerate(recent_codes, start=1):
        code_blocks.append(f"[失败代码 {index}]\n{failed_code}")
    return (
        f"{error_text}\n\n"
        f"注意：该平台错误已经连续出现 {repeat_count} 次，说明之前的修复没有解决根因。\n"
        "请不要重复最近失败代码的结构；必须先定位哪个算子/参数导致该错误，再输出新的可运行 Fast Expression。\n"
        "如果错误提到某个 input index 必须是 vector/matrix/scalar，请按平台实际类型要求改写该算子调用，必要时简化表达式但保留核心研究方向。\n\n"
        "最近失败代码：\n"
        + "\n\n".join(code_blocks)
    )


def invalid_placeholder_reason(code: str) -> str:
    if "{" in code or "}" in code:
        return "代码包含花括号占位符，例如 {data}，WorldQuant Fast Expression 不接受占位符"
    if re.search(r"<\s*(?:field|data|your_data|alpha|expression|template|placeholder|[A-Za-z_][A-Za-z0-9_]*_PLACEHOLDER)\s*>|your_data|DATA_PLACEHOLDER|placeholder", code, re.I):
        return "代码包含未替换的数据占位符"
    return ""


def is_syntax_error_text(text: str) -> bool:
    return bool(
        re.search(
            r"unknown operator|inaccessible|Invalid number of inputs|invalid input|Unexpected|unknown variable|trade_when|At least one of|must be|should be|syntax|operator",
            text or "",
            re.I,
        )
    )


def fail_if_syntax_exhausted(
    item: TemplateItem,
    alpha_name: str,
    code: str,
    reason: str,
    count: int,
    limit: int,
    screenshot: str = "",
) -> None:
    if count < limit:
        return
    failure = TemplateFailure(
        template_file=item.path,
        alpha_name=alpha_name,
        code=code,
        reason=f"连续 Fast Expression 语法错误达到 {limit} 次，停止该模板：{reason}",
        screenshot=screenshot,
    )
    log_iteration(item, alpha_name, count, "template_failed", code, failure.reason, None, {}, "", screenshot)
    raise TemplateFailedError(failure)


def log_iteration(
    item: TemplateItem,
    alpha_name: str,
    iteration: int,
    stage: str,
    code: str,
    platform_error: str,
    quality: QualityReport | None,
    metrics: dict[str, float],
    ds_response: str,
    screenshot: str,
    behavior_family: str = "",
    estimated_self_corr: float | str = "",
    platform_sc: dict[str, Any] | None = None,
) -> None:
    metrics_payload = apply_correlation_quality(metrics if isinstance(metrics, dict) else {})
    sc_payload = sc_payload_from_metrics(metrics_payload, platform_sc)
    platform_sc_json = json.dumps(platform_sc, ensure_ascii=False, default=str) if isinstance(platform_sc, dict) else ""
    append_csv(
        ITERATION_LOG_FILE,
        ITERATION_LOG_FIELDS,
        {
            "time": datetime.now().isoformat(timespec="seconds"),
            "template_file": item.path,
            "alpha_name": alpha_name,
            "iteration": iteration,
            "stage": stage,
            "code": code,
            "platform_error": platform_error,
            "quality_json": json.dumps(quality.to_dict(), ensure_ascii=False) if quality else "",
            "metrics_json": json.dumps(metrics_payload, ensure_ascii=False),
            "ds_response": ds_response,
            "screenshot": screenshot,
            "behavior_family": behavior_family,
            "estimated_self_corr": estimated_self_corr
            if estimated_self_corr not in (None, "")
            else metrics_payload.get("estimated_self_corr", ""),
            "platform_sc_status": sc_payload.get("platform_sc_status", ""),
            "platform_sc_max": sc_payload.get("platform_sc_max", ""),
            "platform_sc_min": sc_payload.get("platform_sc_min", ""),
            "platform_sc_abs_max": sc_payload.get("platform_sc_abs_max", ""),
            "real_self_corr": sc_payload.get("real_self_corr", ""),
            "sc_source": sc_payload.get("sc_source", ""),
            "correlation_quality": sc_payload.get("correlation_quality", ""),
            "submission_quality": sc_payload.get("submission_quality", ""),
            "platform_sc_json": platform_sc_json,
        },
    )


def maybe_record_sidecar_pre_backtest(
    sidecar: SidecarContract,
    config,
    *,
    alpha_name: str,
    code: str,
    metrics: dict[str, float],
    candidate_pool: CandidatePool,
    evolution_memory: EvolutionMemory,
) -> dict[str, object]:
    if not bool(getattr(config, "enable_sidecar_evolution", False)):
        return {}
    try:
        return sidecar.pre_backtest(
            {
                "alpha_id": alpha_name,
                "expression": code,
                "metrics": metrics,
            },
            population=candidate_pool._read(),
            lineage_history=evolution_memory.load_recent_history(limit=200),
            enable_population_overlay=bool(getattr(config, "enable_population_engine", False)),
            enable_policy_hint=bool(getattr(config, "enable_evolution_policy", False)),
            enable_simulator=bool(getattr(config, "enable_alpha_simulator", False)),
        )
    except Exception as exc:
        logging.warning("Sidecar pre-backtest annotation skipped: %s", exc)
        return {}


def maybe_record_sidecar_post_backtest(
    sidecar: SidecarContract,
    config,
    *,
    alpha_name: str,
    code: str,
    result: SimulationResult,
) -> dict[str, object]:
    if not bool(getattr(config, "enable_sidecar_evolution", False)):
        return {}
    quality = result.quality
    try:
        return sidecar.post_backtest(
            {"alpha_id": alpha_name, "expression": code, **sc_payload_from_metrics(result.metrics, result.platform_sc)},
            metrics=result.metrics,
            quality_passed=bool(quality.passed) if quality else False,
            template_success=bool(result.template_success),
        )
    except Exception as exc:
        logging.warning("Sidecar post-backtest annotation skipped: %s", exc)
        return {}


def build_mutation_context(
    code: str,
    metrics: dict[str, float],
    plan,
    memory: EvolutionMemory,
    *,
    candidate_pool: CandidatePool | None = None,
    v2_enabled: bool = True,
    behavior_sc_enabled: bool = True,
    scheduler: AdaptiveMutationScheduler | None = None,
    lineage_depth: int = 0,
    template_controller: object | None = None,
    enable_exploration_pressure: bool = True,
    insight_manager: InsightManager | None = None,
    insight_top_k: int = 5,
) -> dict[str, object]:
    operator_graph = OperatorGraph.from_statistics(memory.get_operator_statistics())
    context = {
        "current_expression": code,
        "current_metrics": metrics,
        "mutation_goal": plan.mutation_goal,
        "allowed_mutations": plan.allowed_mutations,
        "allowed_structural_mutations": getattr(plan, "allowed_structural_mutations", []),
        "forbidden_mutations": plan.forbidden_mutations,
        "current_strategy": getattr(plan, "current_strategy", ""),
        "ast_summary": getattr(plan, "ast_summary", {}),
        "operator_graph_recommendations": operator_graph.recommendations(limit=5),
        "similarity_threshold": getattr(plan, "similarity_threshold", 0.85),
        "diversity_requirement": getattr(
            plan,
            "diversity_requirement",
            "Preserve branch diversity and avoid semantically duplicate alpha candidates.",
        ),
        "complexity": complexity_score(code),
        "complexity_limit": plan.complexity_limit,
        "historical_successful_mutations": memory.get_best_mutations(limit=5),
        "recent_failed_patterns": memory.get_failure_patterns(limit=5),
        "operator_statistics": memory.get_operator_statistics(),
    }
    if v2_enabled:
        fingerprint = build_behavior_fingerprint(code)
        pool_rows = candidate_pool._read() if candidate_pool is not None else []
        estimate = estimate_self_corr(code, pool_rows, metrics=metrics) if behavior_sc_enabled else {}
        active_scheduler = scheduler or AdaptiveMutationScheduler()
        family = str(fingerprint.get("family") or "legacy")
        exploration_pressure = _exploration_pressure(template_controller, family) if enable_exploration_pressure else 0.0
        schedule = active_scheduler.schedule(
            metrics,
            fingerprint,
            estimate,
            lineage_depth=lineage_depth,
            exploration_pressure=exploration_pressure,
        )
        context.update(
            {
                "behavior_family": family,
                "behavior_fingerprint": fingerprint,
                "estimated_self_corr": estimate.get("estimated_self_corr", 0.0) if estimate else 0.0,
                "nearest_behavior_alpha": estimate.get("nearest_alpha_id", "") if estimate else "",
                "mutation_schedule": schedule.to_dict(),
                "exploration_pressure": exploration_pressure,
                "similarity_threshold": schedule.similarity_limit,
                "diversity_requirement": (
                    "Preserve lineage inheritance while reducing behavior overlap through regime, group, bucket, "
                    "or turnover-profile changes before operator rewrites."
                ),
            }
        )
    if insight_manager is not None:
        try:
            insights = insight_manager.format_for_context(context, k=insight_top_k)
        except Exception as exc:
            logging.warning("Research insight injection skipped: %s", exc)
            insights = ""
        if insights:
            context["research_insights"] = insights
    return context


async def maybe_distill_research_insights(
    insight_manager: InsightManager | None,
    ds: DeepSeekClient,
    config,
) -> None:
    if insight_manager is None or not getattr(config, "enable_research_insights", False):
        return
    try:
        generated = await insight_manager.distill_if_due(
            ds,
            interval=max(1, int(getattr(config, "insight_distill_interval", 50))),
            min_samples=max(1, int(getattr(config, "insight_min_samples", 20))),
            max_prompt_clusters=max(1, int(getattr(config, "insight_max_prompt_clusters", 16))),
        )
        if generated:
            logging.info("Research insight distillation generated %s insights", len(generated))
    except Exception as exc:
        logging.warning("Research insight distillation skipped: %s", exc)


def generate_local_structural_candidate(
    parent_code: str,
    parent_metrics: dict[str, float],
    mutation_plan,
    candidate_pool: CandidatePool,
    memory: EvolutionMemory,
    *,
    enable_v2_engine: bool = True,
) -> dict[str, str] | None:
    try:
        ast = ExpressionParser().parse(parent_code)
    except ParseError:
        return None

    limit = mutation_plan.complexity_limit
    constraints = MutationConstraints(
        max_depth=int(limit.get("max_nesting_depth", 8)),
        max_operator_count=int(limit.get("max_operator_count", 24)),
        max_neutralization_layers=int(limit.get("max_neutralization_layers", 2)),
    )
    strategy = StrategyEngine().choose(parent_metrics, memory.load_recent_history(limit=8), memory.get_failure_patterns(limit=5))
    graph = OperatorGraph.from_statistics(memory.get_operator_statistics())
    mutator = StructuralMutator(constraints)
    similarity = SemanticSimilarity(duplicate_threshold=getattr(mutation_plan, "similarity_threshold", 0.85))
    existing = [str(row.get("expression") or "") for row in candidate_pool._read()]

    for candidate in mutator.generate(ast, strategy, constraints, graph):
        duplicate, score = similarity.is_duplicate(candidate.expression, existing)
        if duplicate:
            continue
        controlled_error = validate_controlled_expression(
            parent_code,
            candidate.expression,
            mutation_plan,
            enable_v2_engine=enable_v2_engine,
        )
        if controlled_error:
            continue
        return {
            "expression": candidate.expression,
            "mutation_type": candidate.mutation_type,
            "description": candidate.description,
            "similarity": str(score),
            "source": "structural_mutation",
            "candidate_source": "structural_mutation",
            "is_pending_candidate": True,
        }
    return None


def generate_local_v2_candidate(
    parent_code: str,
    parent_metrics: dict[str, float],
    mutation_plan,
    candidate_pool: CandidatePool,
    memory: EvolutionMemory,
    scheduler: AdaptiveMutationScheduler,
    mutator: RegimeMutator,
    *,
    v2_enabled: bool = True,
    behavior_sc_enabled: bool = True,
    template_controller: object | None = None,
    enable_exploration_pressure: bool = True,
) -> dict[str, object] | None:
    if not v2_enabled:
        return None
    pool_rows = candidate_pool._read()
    fingerprint = build_behavior_fingerprint(parent_code)
    lineage_depth = _lineage_depth(parent_code, pool_rows, memory)
    estimate = estimate_self_corr(parent_code, pool_rows, metrics=parent_metrics) if behavior_sc_enabled else {}
    family = str(fingerprint.get("family") or "legacy")
    exploration_pressure = _exploration_pressure(template_controller, family) if enable_exploration_pressure else 0.0
    schedule = scheduler.schedule(
        parent_metrics,
        fingerprint,
        estimate,
        lineage_depth=lineage_depth,
        exploration_pressure=exploration_pressure,
    )
    if not schedule.recommended_mutations:
        return None

    for candidate in mutator.generate(parent_code, schedule, fingerprint):
        controlled_error = validate_controlled_expression(
            parent_code,
            candidate.expression,
            mutation_plan,
            enable_v2_engine=True,
        )
        if controlled_error:
            continue
        candidate_estimate = estimate_self_corr(candidate.expression, pool_rows, metrics=parent_metrics) if behavior_sc_enabled else {}
        estimated = float(candidate_estimate.get("estimated_self_corr") or 0.0)
        if behavior_sc_enabled and estimated > schedule.similarity_limit:
            continue
        child_fingerprint = build_behavior_fingerprint(candidate.expression)
        return {
            "source": "local_v2_regime_mutator",
            "candidate_source": "local_v2",
            "is_pending_candidate": True,
            "expression": candidate.expression,
            "mutation_type": candidate.mutation_type,
            "description": candidate.description,
            "similarity": str(candidate_estimate.get("max_final_similarity", 0.0) if candidate_estimate else 0.0),
            "behavior_family": child_fingerprint.get("family", "legacy"),
            "behavior_fingerprint": child_fingerprint,
            "estimated_self_corr": estimated,
            "mutation_schedule": schedule.to_dict(),
            "exploration_pressure": exploration_pressure,
            "metadata": candidate.metadata,
        }
    return None


def _lineage_depth(parent_code: str, pool_rows: list[dict[str, object]], memory: EvolutionMemory) -> int:
    fingerprint = code_fingerprint(parent_code)
    for row in pool_rows:
        if code_fingerprint(str(row.get("expression") or "")) == fingerprint:
            try:
                return int(row.get("lineage_depth") or 0)
            except (TypeError, ValueError):
                return 0
    return len([row for row in memory.load_recent_history(limit=200) if str(row.get("expression_after") or "")])


def _exploration_pressure(template_controller: object | None, behavior_family: str) -> float:
    if template_controller is None or not hasattr(template_controller, "pressure_for_family"):
        return 0.0
    try:
        return max(0.0, min(1.0, float(template_controller.pressure_for_family(behavior_family))))
    except (TypeError, ValueError, AttributeError):
        return 0.0


def quality_failure_reason(quality: QualityReport, metrics: dict[str, float]) -> str:
    messages = list(quality.fail_messages or []) + list(quality.pending_messages or [])
    if messages:
        return "; ".join(messages[:4])
    parts: list[str] = []
    if metrics.get("turnover", 0) > 65:
        parts.append("turnover high")
    if metrics.get("fitness", 0) < 1:
        parts.append("fitness low")
    if metrics.get("sharpe", 0) < 0.8:
        parts.append("sharpe too low")
    return "; ".join(parts) or quality.status or "quality not passed"


def record_pending_mutation_result(
    *,
    pending: dict[str, object] | None,
    alpha_name: str,
    iteration: int,
    code: str,
    metrics: dict[str, float],
    quality: QualityReport,
    template_success: bool = False,
    template_success_reason: str = "",
    reward_engine: RewardEngine,
    evolution_memory: EvolutionMemory,
    candidate_pool: CandidatePool,
    v2_enabled: bool = True,
    behavior_sc_enabled: bool = True,
    family_manager: FamilyEvolutionManager | None = None,
    platform_sc: dict[str, Any] | None = None,
) -> float:
    family_manager = family_manager or FamilyEvolutionManager()
    v2_metadata = _record_v2_metadata(
        code=code,
        metrics=metrics,
        pending=pending,
        candidate_pool=candidate_pool,
        family_manager=family_manager,
        v2_enabled=v2_enabled,
        behavior_sc_enabled=behavior_sc_enabled,
        platform_sc=platform_sc,
    )
    candidate_metadata = _candidate_metadata_kwargs(v2_metadata)
    candidate_sc_kwargs = _candidate_platform_sc_kwargs(metrics, platform_sc)
    feedback_allowed = strong_feedback_allowed(metrics)
    if not pending:
        candidate_pool.add_candidate(
            alpha_id=f"{alpha_name}:{iteration}",
            expression=code,
            metrics=metrics,
            reward=0.0,
            mutation_type="initial_or_untracked",
            passed=quality.passed,
            template_success=template_success,
            template_success_reason=template_success_reason,
            **candidate_metadata,
            **candidate_sc_kwargs,
        )
        reward_engine.record_evolution_feedback(
            alpha_id=f"{alpha_name}:{iteration}",
            reward=0.0,
            passed=(quality.passed or template_success) and feedback_allowed,
            generation=iteration,
            template=str(v2_metadata.get("behavior_family") or "legacy"),
            operator="initial_or_untracked",
            parent_id=alpha_name,
            lineage_depth=int(v2_metadata.get("lineage_depth") or 0),
            pool_rows=candidate_pool._read(),
        )
        return 0.0

    before_metrics = pending.get("metrics_before") if isinstance(pending.get("metrics_before"), dict) else {}
    expression_before = str(pending.get("expression_before") or "")
    mutation_type = str(pending.get("mutation_type") or "unknown")
    alpha_id = f"{alpha_name}:{iteration}"
    reward = reward_engine.calculate_reward(
        before_metrics,
        metrics,
        code,
        alpha_id=alpha_id,
        migration_context={
            "template_success": template_success,
            "template_success_reason": template_success_reason,
            "generation": iteration,
            "mutation_type": mutation_type,
            "lineage_root": str(pending.get("parent_id") or alpha_name),
            **sc_payload_from_metrics(metrics, platform_sc),
            **_migration_v2_context(v2_metadata),
        },
    )
    delta = metric_delta(before_metrics, metrics)
    evolution_memory.save_mutation(
        alpha_id=alpha_id,
        parent_id=str(pending.get("parent_id") or alpha_name),
        expression_before=expression_before,
        expression_after=code,
        mutation_type=mutation_type,
        metrics_before=before_metrics,
        metrics_after=metrics,
        delta=delta,
        passed=reward > 0 and feedback_allowed,
        reward=reward,
        quality_passed=quality.passed,
        failure_reason=str(pending.get("failure_reason") or ""),
        complexity_before=complexity_score(expression_before),
        complexity_after=complexity_score(code),
        behavior_family=str(v2_metadata.get("behavior_family") or ""),
        behavior_fingerprint=v2_metadata.get("behavior_fingerprint") if isinstance(v2_metadata.get("behavior_fingerprint"), dict) else None,
        estimated_self_corr=v2_metadata.get("estimated_self_corr") if "estimated_self_corr" in v2_metadata else None,
        family_reward_inheritance=v2_metadata.get("family_reward_inheritance")
        if isinstance(v2_metadata.get("family_reward_inheritance"), dict)
        else None,
        lineage_depth=int(v2_metadata.get("lineage_depth") or 0),
    )
    migration_decision = reward_engine.last_migration_decision
    reward_breakdown = reward_engine.last_breakdown
    reward_breakdown_payload = reward_breakdown.to_dict() if hasattr(reward_breakdown, "to_dict") else reward_breakdown
    candidate_pool.add_candidate(
        alpha_id=alpha_id,
        expression=code,
        metrics=metrics,
        reward=reward,
        mutation_type=mutation_type,
        passed=quality.passed,
        reward_breakdown=reward_breakdown_payload if isinstance(reward_breakdown_payload, dict) else None,
        legacy_reward=_breakdown_value(reward_breakdown, "legacy_reward"),
        v2_reward=_breakdown_value(reward_breakdown, "final_reward"),
        effective_reward=reward,
        migration_state=migration_decision.state.value if migration_decision else "",
        migration_weights={
            "legacy": migration_decision.legacy_weight,
            "v2": migration_decision.v2_weight,
        }
        if migration_decision
        else None,
        template_success=template_success,
        template_success_reason=template_success_reason,
        **candidate_metadata,
        **candidate_sc_kwargs,
    )
    reward_engine.record_evolution_feedback(
        alpha_id=alpha_id,
        reward=reward,
        passed=(reward > 0 or quality.passed) and feedback_allowed,
        generation=iteration,
        template=str(v2_metadata.get("behavior_family") or "legacy"),
        operator=mutation_type,
        parent_id=str(pending.get("parent_id") or alpha_name),
        lineage_depth=int(v2_metadata.get("lineage_depth") or 0),
        pool_rows=candidate_pool._read(),
    )
    if feedback_allowed and (reward > 0 or quality.passed or template_success):
        evolution_memory.record_successful_fix(successful_fix=code)
    return reward


def _record_v2_metadata(
    *,
    code: str,
    metrics: dict[str, float],
    pending: dict[str, object] | None,
    candidate_pool: CandidatePool,
    family_manager: FamilyEvolutionManager,
    v2_enabled: bool,
    behavior_sc_enabled: bool,
    platform_sc: dict[str, Any] | None = None,
) -> dict[str, object]:
    metrics = apply_correlation_quality(metrics)
    if not v2_enabled:
        return {"enable_v2_metadata": False, **sc_payload_from_metrics(metrics, platform_sc)}
    fingerprint = build_behavior_fingerprint(code)
    family = str(fingerprint.get("family") or "legacy")
    estimate = estimate_self_corr(code, candidate_pool._read(), metrics=metrics) if behavior_sc_enabled else {}
    parent_family = str((pending or {}).get("parent_family") or (pending or {}).get("behavior_family") or "legacy")
    inheritance = (pending or {}).get("family_reward_inheritance")
    if not isinstance(inheritance, dict):
        inheritance = family_manager.inheritance_metadata(
            parent_family=parent_family,
            child_family=family,
            parent_reward=0.0,
        )
    if "estimated_self_corr" not in metrics and estimate:
        try:
            metrics["estimated_self_corr"] = float(estimate.get("estimated_self_corr") or 0.0)
        except (TypeError, ValueError):
            pass
        metrics = apply_correlation_quality(metrics)
    return {
        "behavior_family": family,
        "behavior_fingerprint": fingerprint,
        "estimated_self_corr": float(estimate.get("estimated_self_corr") or (pending or {}).get("estimated_self_corr") or 0.0),
        "family_reward_inheritance": inheritance,
        "lineage_depth": int((pending or {}).get("lineage_depth") or 0),
        "enable_v2_metadata": True,
        **sc_payload_from_metrics(metrics, platform_sc),
    }


def _candidate_metadata_kwargs(metadata: dict[str, object]) -> dict[str, object]:
    allowed = {
        "behavior_family",
        "behavior_fingerprint",
        "estimated_self_corr",
        "family_reward_inheritance",
        "lineage_depth",
        "enable_v2_metadata",
    }
    return {key: value for key, value in metadata.items() if key in allowed}


def _candidate_platform_sc_kwargs(metrics: dict[str, Any] | None, platform_sc: dict[str, Any] | None = None) -> dict[str, Any]:
    metrics = metrics if isinstance(metrics, dict) else {}
    payload = platform_sc if isinstance(platform_sc, dict) else None

    def value_for(metric_key: str, payload_key: str) -> Any:
        value = metrics.get(metric_key)
        if value in (None, "") and payload is not None:
            value = payload.get(payload_key)
        return value

    result: dict[str, Any] = {
        "platform_sc_status": str((payload or {}).get("status") or metrics.get("platform_sc_status") or ""),
        "platform_sc_payload": payload,
    }
    for target, metric_key, payload_key in (
        ("platform_sc_max", "platform_sc_max", "max"),
        ("platform_sc_min", "platform_sc_min", "min"),
        ("platform_sc_abs_max", "platform_sc_abs_max", "abs_max"),
    ):
        value = value_for(metric_key, payload_key)
        if value not in (None, ""):
            result[target] = value
    return result


def _migration_v2_context(metadata: dict[str, object]) -> dict[str, object]:
    return {
        key: value
        for key, value in metadata.items()
        if key
        in {
            "behavior_family",
            "behavior_fingerprint",
            "estimated_self_corr",
            "platform_sc",
            "platform_sc_status",
            "platform_sc_max",
            "platform_sc_min",
            "platform_sc_abs_max",
            "real_self_corr",
            "sc_source",
            "correlation_quality",
            "submission_quality",
            "family_reward_inheritance",
            "lineage_depth",
        }
    }


def _breakdown_value(breakdown: object, key: str) -> float | None:
    if isinstance(breakdown, dict):
        value = breakdown.get(key)
    else:
        value = getattr(breakdown, key, None)
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def print_success(success: TemplateSuccess) -> None:
    payload = {
        "template_file": success.template_file,
        "alpha_name": success.alpha_name,
        "metrics": success.metrics,
        "quality": success.quality.to_dict(),
        "favorite_screenshot": success.screenshot,
        "template_success": success.template_success,
        "template_success_reason": success.template_success_reason,
    }
    line = "SUCCESS_RESULT " + json.dumps(payload, ensure_ascii=False)
    print(line, flush=True)
    logging.info(line)


def print_failure(failure: TemplateFailure) -> None:
    payload = {
        "template_file": failure.template_file,
        "alpha_name": failure.alpha_name,
        "reason": failure.reason,
        "screenshot": failure.screenshot,
    }
    line = "FAILURE_RESULT " + json.dumps(payload, ensure_ascii=False)
    print(line, flush=True)
    logging.warning(line)


def run() -> int:
    return asyncio.run(main())
