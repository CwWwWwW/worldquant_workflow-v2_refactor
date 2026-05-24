from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from playwright.async_api import Page

from . import watchdog
from .browser_supervisor import AlphaBrowserSession, BrowserSupervisor
from .browser_ops import (
    ensure_authenticated,
    ensure_authenticated_if_needed,
    goto_page,
    safe_click,
    set_editor_text,
    wait_visible_any,
)
from .config import selector_config
from .correlation import check_self_correlation, extract_structure
from .failure_artifacts import capture_failure_artifacts
from .logger_state import STATE_FATAL, STATE_PROGRESS, log_recovery_sidecar, log_state_event
from .favorites import add_to_favorites
from .models import SIMULATE_URL, PlatformError, QualityReport, RunValidation, SimulationResult, WorkflowConfig
from .page_healthcheck import page_healthcheck
from .paths import ITERATION_DIR, now_ts
from .platform_sc import apply_platform_sc_to_metrics, save_platform_sc_artifacts, wait_and_extract_platform_sc
from .quality import extract_metrics, looks_like_quality_advice, parse_quality_report
from .recovery import RecoveryLevel
from .safe_io import trim_old_files
from .storage import is_io_degraded
from .run_validator import (
    RunValidationError,
    STALE_RESULT,
    read_result_timestamp,
    read_simulation_id,
    validate_result_freshness,
    validate_run_triggered,
)
from .template_success_detector import (
    RESULT_UNCERTAIN,
    SUCCESS_CANDIDATE,
    TemplateSuccessDetection,
    confirm_success_candidate,
    detect_template_success,
    emit_template_success_event,
)
from .workflow_state import NonRecoverableStateError, StatePolicy, WorkflowFSM, WorkflowState, WorkflowStateError


ALPHA_DETAILS_SETTINGS_ERROR = "[AUTOMATION] result_panel_obstructed_by_alpha_details_settings"
SUCCESS_CONFIRM_POLLS = 4
SUCCESS_CONFIRM_INTERVAL = 3
SUCCESS_CANDIDATE_STABLE_READS = 2
FINAL_RECOVERY_DELAY = 15
WAIT_RESULT_MIN_SECONDS = 240
WAIT_RESULT_DEFAULT_MAX_SECONDS = 300
WAIT_RESULT_START_TIMEOUT_SECONDS = 90
RESULT_STABLE_READS = 3
RESULT_POLL_INTERVAL_SECONDS = 2.0
RESULT_DOM_STABLE_WINDOW_SECONDS = 4.0


@dataclass
class SimulateSelectors:
    editor: list[str]
    name: list[str]
    run: list[str]


@dataclass
class SimulateFSMContext:
    supervisor: BrowserSupervisor
    session: AlphaBrowserSession
    page: Page
    code: str
    alpha_name: str
    config: WorkflowConfig
    selectors: SimulateSelectors
    template_file: str = ""
    baseline: str = ""
    baseline_progress: float | None = None
    old_simulation_id: str = ""
    new_simulation_id: str = ""
    click_timestamp: float = 0.0
    simulation_session_id: str = ""
    observed_start: bool = False
    page_text: str = ""
    metrics: dict[str, float] | None = None
    quality: QualityReport | None = None
    screenshot: str = ""
    result_timestamp: float | None = None
    result_fingerprint: str = ""
    freshness_score: int | None = None
    result_stable_count: int = 0
    progress_complete: bool = False
    metrics_stable: bool = False
    final_correlation_error: str = ""
    template_success: bool = False
    template_success_reason: str = ""
    success_candidate: bool = False
    result_uncertain: bool = False
    platform_sc: dict[str, Any] = field(default_factory=dict)
    platform_sc_checked: bool = False


def simulate_selectors(config: WorkflowConfig) -> SimulateSelectors:
    return SimulateSelectors(
        editor=selector_config(
            config,
            "simulate_editor",
            ["textarea", ".monaco-editor textarea", ".cm-content", '[contenteditable="true"]', '[role="textbox"]'],
        ),
        name=selector_config(
            config,
            "simulate_name",
            ['input[name="name"]', 'input[placeholder*="name" i]', 'input[aria-label*="name" i]', 'input[type="text"]'],
        ),
        run=selector_config(
            config,
            "simulate_run",
            [
                'button:has-text("Run")',
                'button:has-text("Simulate")',
                '[role="button"]:has-text("Run")',
                '[role="button"]:has-text("Simulate")',
                'button:has(.editor-simulate-button-text)',
                '[role="button"]:has(.editor-simulate-button-text)',
            ],
        ),
    )


async def run_platform_backtest(page: Page, code: str, alpha_name: str, config: WorkflowConfig) -> SimulationResult:
    return await _run_platform_backtest_once(page, code, alpha_name, config)


async def run_platform_backtest_attempt(
    supervisor: BrowserSupervisor,
    *,
    code: str,
    alpha_name: str,
    config: WorkflowConfig,
    template_file: str = "",
) -> SimulationResult:
    recovery_attempts = 0
    browser_restart_attempts = 0
    while True:
        session = await supervisor.new_alpha_session(alpha_name)
        try:
            result = await run_alpha_fsm(
                supervisor=supervisor,
                session=session,
                code=code,
                alpha_name=alpha_name,
                config=config,
                template_file=template_file,
            )
        finally:
            await supervisor.close_session(session, persist_storage=False)

        if result.ok:
            return result

        if result.error and not is_automation_result_error(result.error.text):
            return result

        recovery_level = result.recovery_level or RecoveryLevel.LEVEL_3_REBUILD_CONTEXT.name
        if recovery_level in {
            RecoveryLevel.LEVEL_1_RELOAD_PAGE.name,
            RecoveryLevel.LEVEL_2_RECREATE_PAGE.name,
            RecoveryLevel.LEVEL_3_REBUILD_CONTEXT.name,
        }:
            recovery_attempts += 1
            if recovery_attempts > 2:
                return result
            logging.warning(
                "Alpha %s will retry after context/page recovery: level=%s attempt=%s",
                alpha_name,
                recovery_level,
                recovery_attempts,
            )
            continue

        if recovery_level == RecoveryLevel.LEVEL_4_RESTART_BROWSER.name:
            browser_restart_attempts += 1
            if browser_restart_attempts > 1:
                return result
            logging.warning("Alpha %s will retry after browser restart", alpha_name)
            await supervisor.restart_browser()
            continue

        if recovery_level == RecoveryLevel.LEVEL_5_KILL_CHROMIUM.name:
            browser_restart_attempts += 1
            if browser_restart_attempts > 1:
                return result
            logging.warning("Alpha %s will retry after Chromium kill/restart", alpha_name)
            await supervisor.kill_and_restart_browser()
            continue

        return result


async def run_alpha_fsm(
    *,
    supervisor: BrowserSupervisor,
    session: AlphaBrowserSession,
    code: str,
    alpha_name: str,
    config: WorkflowConfig,
    template_file: str = "",
) -> SimulationResult:
    fsm_context = SimulateFSMContext(
        supervisor=supervisor,
        session=session,
        page=session.page,
        code=code,
        alpha_name=alpha_name,
        config=config,
        selectors=simulate_selectors(config),
        template_file=template_file,
    )
    handlers = {
        WorkflowState.INIT: lambda: fsm_init(fsm_context),
        WorkflowState.AUTH_CHECK: lambda: fsm_auth_check(fsm_context),
        WorkflowState.OPEN_SIMULATE: lambda: fsm_open_simulate(fsm_context),
        WorkflowState.EDITOR_READY: lambda: fsm_editor_ready(fsm_context),
        WorkflowState.WRITE_CODE: lambda: fsm_write_code(fsm_context),
        WorkflowState.WRITE_NAME: lambda: fsm_write_name(fsm_context),
        WorkflowState.CLICK_RUN: lambda: fsm_click_run(fsm_context),
        WorkflowState.WAIT_QUEUE: lambda: fsm_wait_queue(fsm_context),
        WorkflowState.WAIT_RESULT: lambda: fsm_wait_result(fsm_context),
        WorkflowState.PARSE_RESULT: lambda: fsm_parse_result(fsm_context),
        WorkflowState.QUALITY_CHECK: lambda: fsm_quality_check(fsm_context),
        WorkflowState.ADD_FAVORITE: lambda: fsm_add_favorite(fsm_context),
        WorkflowState.FINISHED: lambda: fsm_finished(fsm_context),
    }
    fsm = WorkflowFSM(alpha_id=alpha_name, handlers=handlers, recover=lambda state, policy, exc, retry: fsm_recover(fsm_context, state, policy, exc, retry))
    browser_failure: asyncio.Future[BaseException] = asyncio.get_running_loop().create_future()

    async def on_browser_unhealthy(exc: BaseException) -> None:
        if not browser_failure.done():
            browser_failure.set_result(exc)
        log_state_event(
            STATE_FATAL,
            alpha_id=alpha_name,
            state="BROWSER_WATCHDOG",
            error=str(exc),
            recovery=RecoveryLevel.LEVEL_4_RESTART_BROWSER.name,
        )
        log_recovery_sidecar(
            "BrowserRecovery",
            action="WATCHDOG_UNHEALTHY",
            alpha_id=alpha_name,
            state="BROWSER_WATCHDOG",
            recovery=RecoveryLevel.LEVEL_4_RESTART_BROWSER.name,
            error=str(exc),
        )
        log_recovery_sidecar(
            "FullRebuild",
            action="RESTART_BROWSER",
            alpha_id=alpha_name,
            state="BROWSER_WATCHDOG",
            recovery=RecoveryLevel.LEVEL_4_RESTART_BROWSER.name,
        )
        log_recovery_sidecar(
            "CircuitBreaker",
            action="OPEN_BROWSER_WATCHDOG",
            alpha_id=alpha_name,
            state="BROWSER_WATCHDOG",
            recovery=RecoveryLevel.LEVEL_4_RESTART_BROWSER.name,
        )

    browser_watchdog_task = asyncio.create_task(
        watchdog.browser_watchdog_loop(
            lambda: supervisor.browser,
            lambda: fsm_context.page,
            on_browser_unhealthy,
            interval_seconds=10,
            timeout=5,
        )
    )
    alpha_task = asyncio.create_task(watchdog.alpha(alpha_name, fsm.run(), timeout=25 * 60))
    try:
        done, _ = await asyncio.wait({alpha_task, browser_failure}, return_when=asyncio.FIRST_COMPLETED)
        if browser_failure in done:
            exc = browser_failure.result()
            alpha_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await alpha_task
            artifacts = await capture_failure_artifacts(
                fsm_context.page,
                alpha_id=alpha_name,
                state="BROWSER_WATCHDOG",
                context=fsm_context.page.context if fsm_context.page else None,
            )
            page_text = await safe_body_text(fsm_context.page)
            return SimulationResult(
                ok=False,
                code=code,
                alpha_name=alpha_name,
                error=PlatformError(f"[AUTOMATION] browser_watchdog: {exc}", page_text),
                page_text=page_text,
                screenshot=artifacts.screenshot,
                state_trace=fsm.trace,
                recovery_level=RecoveryLevel.LEVEL_4_RESTART_BROWSER.name,
            )
        state_trace = await alpha_task
    except WorkflowStateError as exc:
        artifacts = await capture_failure_artifacts(
            fsm_context.page,
            alpha_id=alpha_name,
            state=exc.state.name,
            context=fsm_context.page.context if fsm_context.page else None,
        )
        page_text = await safe_body_text(fsm_context.page)
        raw_error = str(exc)
        error_text = raw_error if exc.nonrecoverable else f"[AUTOMATION] {exc.state.name}: {exc}"
        return SimulationResult(
            ok=False,
            code=code,
            alpha_name=alpha_name,
            error=PlatformError(error_text, page_text),
            page_text=page_text,
            screenshot=artifacts.screenshot,
            simulation_id=fsm_context.new_simulation_id or fsm_context.old_simulation_id,
            result_timestamp=fsm_context.result_timestamp,
            simulation_session_id=fsm_context.simulation_session_id,
            result_fingerprint=fsm_context.result_fingerprint,
            freshness_score=fsm_context.freshness_score,
            result_stable_count=fsm_context.result_stable_count,
            state_trace=fsm.trace,
            recovery_level=exc.recovery_level.name,
        )
    except watchdog.WatchdogTimeout as exc:
        artifacts = await capture_failure_artifacts(
            fsm_context.page,
            alpha_id=alpha_name,
            state="ALPHA_WATCHDOG",
            context=fsm_context.page.context if fsm_context.page else None,
        )
        log_state_event(STATE_FATAL, alpha_id=alpha_name, state="ALPHA_WATCHDOG", error=str(exc), recovery=RecoveryLevel.LEVEL_3_REBUILD_CONTEXT.name)
        page_text = await safe_body_text(fsm_context.page)
        return SimulationResult(
            ok=False,
            code=code,
            alpha_name=alpha_name,
            error=PlatformError(f"[AUTOMATION] alpha_watchdog_timeout: {exc}", page_text),
            page_text=page_text,
            screenshot=artifacts.screenshot,
            state_trace=fsm.trace,
            recovery_level=RecoveryLevel.LEVEL_3_REBUILD_CONTEXT.name,
        )
    except Exception as exc:
        artifacts = await capture_failure_artifacts(
            fsm_context.page,
            alpha_id=alpha_name,
            state="UNHANDLED",
            context=fsm_context.page.context if fsm_context.page else None,
        )
        page_text = await safe_body_text(fsm_context.page)
        return SimulationResult(
            ok=False,
            code=code,
            alpha_name=alpha_name,
            error=PlatformError(f"[AUTOMATION] unhandled_fsm_error: {exc}", page_text),
            page_text=page_text,
            screenshot=artifacts.screenshot,
            state_trace=fsm.trace,
            recovery_level=RecoveryLevel.LEVEL_3_REBUILD_CONTEXT.name,
        )
    finally:
        browser_watchdog_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await browser_watchdog_task
        if not alpha_task.done():
            alpha_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await alpha_task

    return SimulationResult(
        ok=True,
        code=code,
        alpha_name=alpha_name,
        metrics=fsm_context.metrics or {},
        quality=fsm_context.quality,
        page_text=fsm_context.page_text,
        screenshot=fsm_context.screenshot,
        simulation_id=fsm_context.new_simulation_id or fsm_context.old_simulation_id,
        result_timestamp=fsm_context.result_timestamp,
        simulation_session_id=fsm_context.simulation_session_id,
        result_fingerprint=fsm_context.result_fingerprint,
        freshness_score=fsm_context.freshness_score,
        result_stable_count=fsm_context.result_stable_count,
        state_trace=state_trace,
        template_success=fsm_context.template_success,
        template_success_reason=fsm_context.template_success_reason,
        success_candidate=fsm_context.success_candidate,
        result_uncertain=fsm_context.result_uncertain,
        platform_sc=fsm_context.platform_sc,
    )


async def fsm_init(ctx: SimulateFSMContext) -> None:
    await watchdog.browser_healthy(ctx.supervisor.browser, ctx.page)


async def fsm_auth_check(ctx: SimulateFSMContext) -> None:
    await ensure_authenticated(ctx.page, ctx.config, target_url=SIMULATE_URL)


async def fsm_open_simulate(ctx: SimulateFSMContext) -> None:
    await wait_visible_any(ctx.page, selector_config(ctx.config, "simulate_ready", ["body"]), timeout=30000)
    await ensure_simulate_auth(ctx.page, ctx.config, "fsm_after_initial_ready", rerun_on_reauth=False)


async def fsm_editor_ready(ctx: SimulateFSMContext) -> None:
    await ensure_code_editor_visible(ctx.page)
    health = await page_healthcheck(ctx.page)
    if not health.ok:
        raise AutomationFlowError(f"[AUTOMATION] page_healthcheck_failed:{';'.join(health.reasons)}")
    await ensure_simulate_auth(ctx.page, ctx.config, "fsm_after_editor_visible", rerun_on_reauth=False)
    await dismiss_page_obstructions(ctx.page, "fsm_before_baseline")
    ctx.baseline = await collect_pre_run_baseline(ctx.page)
    ctx.old_simulation_id = await read_simulation_id(ctx.page)


async def fsm_write_code(ctx: SimulateFSMContext) -> None:
    await ensure_simulate_auth(ctx.page, ctx.config, "fsm_before_editor_write")
    await set_editor_text(ctx.page, ctx.selectors.editor, ctx.code)
    await ensure_simulate_auth(ctx.page, ctx.config, "fsm_after_editor_write")


async def fsm_write_name(ctx: SimulateFSMContext) -> None:
    await ensure_simulate_auth(ctx.page, ctx.config, "fsm_before_alpha_name")
    await ensure_alpha_name(ctx.page, ctx.selectors.name, ctx.alpha_name)
    await ensure_simulate_auth(ctx.page, ctx.config, "fsm_after_alpha_name")


async def fsm_click_run(ctx: SimulateFSMContext) -> None:
    ctx.baseline_progress = await read_progress(ctx.page)
    await ensure_simulate_auth(ctx.page, ctx.config, "fsm_before_run_click")
    await ensure_alpha_details_settings_not_blocking_run(ctx.page, "fsm_before_run_click")
    ctx.click_timestamp = time.time()
    alpha_name = getattr(ctx, "alpha_name", "alpha")
    ctx.simulation_session_id = f"{alpha_name}-{int(ctx.click_timestamp)}-{uuid.uuid4().hex[:8]}"
    await click_run_button(ctx.page, ctx.selectors.run)
    run_validation = await validate_run_triggered(
        ctx.page,
        old_simulation_id=ctx.old_simulation_id,
        click_timestamp=ctx.click_timestamp,
        timeout=3,
    )
    if run_validation.ok:
        ctx.new_simulation_id = run_validation.new_simulation_id
        ctx.observed_start = True
        return
    ctx.new_simulation_id = run_validation.new_simulation_id
    ctx.observed_start = await run_start_signal_seen(ctx.page, timeout_seconds=12, baseline_progress=ctx.baseline_progress)
    if ctx.observed_start:
        logging.info(
            "Run trigger confirmed by page activity without simulation id change: old=%s new=%s",
            ctx.old_simulation_id,
            ctx.new_simulation_id,
        )
        return


async def fsm_wait_queue(ctx: SimulateFSMContext) -> None:
    if ctx.observed_start:
        return
    ctx.observed_start = await run_start_signal_seen(ctx.page, timeout_seconds=30, baseline_progress=ctx.baseline_progress)
    if not ctx.observed_start:
        raise AutomationFlowError("[AUTOMATION] run_queue_not_observed")


async def fsm_wait_result(ctx: SimulateFSMContext) -> None:
    ctx.page_text = await wait_for_backtest_finished(
        ctx.page,
        ctx.config,
        ctx.baseline,
        ctx.observed_start,
        baseline_progress=ctx.baseline_progress,
        alpha_id=ctx.alpha_name,
        simulation_session_id=ctx.simulation_session_id,
    )
    ctx.result_fingerprint = stable_result_fingerprint(ctx.page_text)
    ctx.result_stable_count = max(ctx.result_stable_count, result_stable_reads(ctx.config))
    ctx.progress_complete = True
    ctx.metrics_stable = bool(ctx.result_fingerprint)


async def fsm_parse_result(ctx: SimulateFSMContext) -> None:
    await ensure_simulate_auth(ctx.page, ctx.config, "fsm_before_result_collect")
    await ensure_alpha_details_settings_closed(ctx.page, "fsm_before_result_collect")
    validation = await collect_and_validate_result_with_stale_downgrade(ctx)
    ctx.freshness_score = validation.freshness_score
    ctx.result_timestamp = validation.result_timestamp or await read_result_timestamp(ctx.page)
    ctx.result_fingerprint = validation.result_fingerprint or stable_result_fingerprint(ctx.page_text)
    ctx.result_stable_count = max(ctx.result_stable_count, validation.result_stable_count)
    ctx.page_text, detection = await stabilize_success_visibility(
        ctx.page,
        ctx.config,
        ctx.page_text,
        alpha_name=ctx.alpha_name,
        code=ctx.code,
        template_file=ctx.template_file,
        simulation_id=ctx.new_simulation_id or ctx.old_simulation_id,
    )
    ctx.quality = parse_quality_report(ctx.page_text)
    ctx.metrics = extract_metrics(ctx.page_text)
    ctx.platform_sc = await run_platform_sc_check_after_backtest(ctx)
    ctx.metrics = apply_platform_sc_to_metrics(ctx.metrics, ctx.platform_sc)
    ctx.template_success = detection.template_success
    ctx.template_success_reason = detection.reason
    ctx.success_candidate = detection.candidate_success
    ctx.result_uncertain = detection.result_uncertain
    if detection.template_success:
        emit_template_success_event(
            alpha_id=ctx.alpha_name,
            detection=detection,
            template_file=ctx.template_file,
            simulation_id=ctx.new_simulation_id or ctx.old_simulation_id,
        )
    ctx.screenshot = await capture_screenshot(ctx.page, ctx.alpha_name, "result")


async def run_platform_sc_check_after_backtest(ctx: SimulateFSMContext) -> dict[str, Any]:
    if getattr(ctx, "platform_sc_checked", False):
        return ctx.platform_sc or {"status": "unknown", "source": "platform"}
    ctx.platform_sc_checked = True
    if not bool(getattr(ctx.config, "enable_platform_sc_check", True)):
        logging.info("[PlatformSC] alpha=%s skipped reason=disabled_by_config", ctx.alpha_name)
        return {"status": "skipped", "source": "platform", "reason": "disabled_by_config"}
    timeout_seconds = max(1, int(getattr(ctx.config, "platform_sc_timeout_seconds", 90) or 90))
    logging.info("[PlatformSC] alpha=%s start after_backtest=true timeout=%s", ctx.alpha_name, timeout_seconds)
    platform_sc = await collect_platform_sc_safely(
        ctx.page,
        alpha_name=ctx.alpha_name,
        timeout_seconds=timeout_seconds,
    )
    ctx.platform_sc = platform_sc
    return platform_sc


async def collect_platform_sc_safely(
    page: Page,
    *,
    alpha_name: str = "",
    timeout_seconds: int = 90,
) -> dict[str, Any]:
    artifact_alpha = re.sub(r"[^A-Za-z0-9_.-]+", "_", alpha_name or "alpha").strip("._") or "alpha"
    try:
        platform_sc = await wait_and_extract_platform_sc(
            page,
            timeout_seconds=timeout_seconds,
            artifact_prefix=f"platform_sc_{artifact_alpha}",
        )
    except Exception as exc:
        logging.warning("[PlatformSC] alpha=%s status=error safe_continue=true error=%s", alpha_name, exc)
        platform_sc = {"status": "error", "source": "platform", "error": str(exc)}
        try:
            platform_sc = await save_platform_sc_artifacts(
                page,
                None,
                platform_sc,
                artifact_prefix=f"platform_sc_{artifact_alpha}",
                timeout=False,
            )
        except Exception:
            logging.debug("[PlatformSC] alpha=%s error artifact save failed", alpha_name, exc_info=True)
    platform_sc = normalize_platform_sc_result(platform_sc)
    log_platform_sc_result(alpha_name, platform_sc)
    return platform_sc


def merge_platform_sc_metrics(metrics: dict[str, float], platform_sc: dict[str, Any] | None) -> dict[str, float]:
    return apply_platform_sc_to_metrics(metrics or {}, platform_sc)  # compatibility wrapper


def normalize_platform_sc_result(platform_sc: dict[str, Any] | None) -> dict[str, Any]:
    result = dict(platform_sc or {})
    result.setdefault("status", "unknown")
    result.setdefault("source", "platform")
    for key in ("max", "min", "abs_max"):
        if key not in result:
            result[key] = None
    if "raw_text_preview" in result:
        result["raw_text_preview"] = str(result.get("raw_text_preview") or "")[:300]
    return result


def log_platform_sc_result(alpha_name: str, platform_sc: dict[str, Any]) -> None:
    status = str(platform_sc.get("status") or "unknown")
    elapsed = platform_sc.get("elapsed_seconds", "")
    artifacts = platform_sc.get("artifacts") if isinstance(platform_sc.get("artifacts"), dict) else {}
    if status == "complete":
        logging.info(
            "[PlatformSC] alpha=%s status=complete max=%s min=%s abs_max=%s selector=%s elapsed=%ss",
            alpha_name,
            platform_sc.get("max"),
            platform_sc.get("min"),
            platform_sc.get("abs_max"),
            platform_sc.get("selector", ""),
            elapsed,
        )
    elif status in {"timeout", "missing", "error"}:
        logging.warning(
            "[PlatformSC] alpha=%s status=%s elapsed=%ss safe_continue=true artifacts=%s error=%s",
            alpha_name,
            status,
            elapsed,
            artifacts,
            platform_sc.get("error", ""),
        )
    else:
        logging.info("[PlatformSC] alpha=%s status=%s elapsed=%ss safe_continue=true", alpha_name, status, elapsed)


async def collect_and_validate_result_with_stale_downgrade(ctx: SimulateFSMContext) -> RunValidation:
    last_validation = RunValidation(ok=False)
    for attempt in range(3):
        if attempt == 1:
            log_state_event(
                STATE_PROGRESS,
                alpha_id=ctx.alpha_name,
                state=WorkflowState.PARSE_RESULT.name,
                simulation_id=ctx.new_simulation_id or ctx.old_simulation_id,
                extra={
                    "simulation_session_id": ctx.simulation_session_id,
                    "stale_recovery_action": "soft_refresh_metrics",
                },
            )
            await soft_refresh_result_metrics(ctx.page)
        elif attempt == 2:
            log_state_event(
                STATE_PROGRESS,
                alpha_id=ctx.alpha_name,
                state=WorkflowState.PARSE_RESULT.name,
                simulation_id=ctx.new_simulation_id or ctx.old_simulation_id,
                extra={
                    "simulation_session_id": ctx.simulation_session_id,
                    "stale_recovery_action": "requery_result_panel",
                },
            )
            await requery_result_panel(ctx.page)

        ctx.page_text = await collect_result_text(ctx.page)
        await ensure_simulate_auth(ctx.page, ctx.config, "fsm_before_quality_parse", current_body=ctx.page_text)
        result_fingerprint_value = stable_result_fingerprint(ctx.page_text)
        metrics_detected = bool(extract_metrics(ctx.page_text))
        progress_complete = ctx.progress_complete
        if not progress_complete:
            progress = await read_progress(ctx.page)
            progress_complete = bool(progress is not None and progress >= 99.9)
        stable_count = ctx.result_stable_count if result_fingerprint_value and result_fingerprint_value == ctx.result_fingerprint else 1
        fingerprint_stable = bool(result_fingerprint_value and (ctx.metrics_stable or stable_count >= result_stable_reads(ctx.config)))
        validation = await validate_result_freshness(
            ctx.page,
            RunValidation(
                ok=True,
                old_simulation_id=ctx.old_simulation_id,
                new_simulation_id=ctx.new_simulation_id,
                click_timestamp=ctx.click_timestamp,
                simulation_session_id=ctx.simulation_session_id,
                result_fingerprint=result_fingerprint_value,
                result_stable_count=stable_count,
                progress_complete=progress_complete,
                metrics_detected=metrics_detected,
                fingerprint_stable=fingerprint_stable,
                freshness_accept_score=ctx.config.freshness_accept_score,
                consistency_signals_present=ctx.config.enable_result_consistency_validation,
            ),
        )
        ctx.result_timestamp = validation.result_timestamp or ctx.result_timestamp
        ctx.result_fingerprint = result_fingerprint_value or ctx.result_fingerprint
        ctx.result_stable_count = stable_count
        ctx.freshness_score = validation.freshness_score
        last_validation = validation
        log_state_event(
            STATE_PROGRESS,
            alpha_id=ctx.alpha_name,
            state=WorkflowState.PARSE_RESULT.name,
            simulation_id=ctx.new_simulation_id or ctx.old_simulation_id,
            extra={
                "simulation_session_id": ctx.simulation_session_id,
                "result_fingerprint": result_fingerprint_value,
                "freshness_score": validation.freshness_score,
                "result_stable_count": stable_count,
                "metrics_stable": fingerprint_stable,
            },
        )
        if validation.ok:
            return validation
    raise RunValidationError(
        f"[AUTOMATION] {STALE_RESULT}: result_timestamp={last_validation.result_timestamp} "
        f"click_timestamp={ctx.click_timestamp} freshness_score={last_validation.freshness_score}"
    )


async def soft_refresh_result_metrics(page: Page) -> None:
    with contextlib.suppress(Exception):
        await reveal_result_panels(page, include_show_test_period=True)
    await asyncio.sleep(1.0)


async def requery_result_panel(page: Page) -> None:
    with contextlib.suppress(Exception):
        await detect_and_click_show_test_period(page)
    with contextlib.suppress(Exception):
        await reveal_result_panels(page, include_show_test_period=True)
    await asyncio.sleep(2.0)


async def stabilize_success_visibility(
    page: Page,
    config: WorkflowConfig,
    text: str,
    *,
    alpha_name: str,
    code: str,
    template_file: str = "",
    simulation_id: str = "",
) -> tuple[str, TemplateSuccessDetection]:
    detection = await detect_current_success_state(page, config, text, code=code)
    if detection.template_success or not detection.candidate_success:
        return text, detection

    logging.info(
        "%s alpha=%s reason=%s signals=%s",
        SUCCESS_CANDIDATE,
        alpha_name,
        detection.reason,
        ",".join(detection.signals),
    )
    latest_text = text
    latest_detection = detection
    last_fingerprint = success_candidate_fingerprint(latest_text)
    stable_reads = 1 if last_fingerprint else 0

    for poll in range(1, SUCCESS_CONFIRM_POLLS + 1):
        await asyncio.sleep(SUCCESS_CONFIRM_INTERVAL)
        try:
            await ensure_simulate_auth(page, config, f"success_candidate_poll_{poll}")
            await reveal_result_panels(page, include_show_test_period=True)
            latest_text = await collect_result_text(page)
            await ensure_simulate_auth(page, config, f"success_candidate_poll_{poll}_after_collect", current_body=latest_text)
        except Exception as exc:
            logging.info("%s poll=%s transient_fetch_failure=%s", RESULT_UNCERTAIN, poll, exc)
            continue

        latest_detection = await detect_current_success_state(page, config, latest_text, code=code)
        logging.info(
            "%s poll=%s template_success=%s candidate=%s reason=%s signals=%s",
            SUCCESS_CANDIDATE,
            poll,
            latest_detection.template_success,
            latest_detection.candidate_success,
            latest_detection.reason,
            ",".join(latest_detection.signals),
        )
        if latest_detection.template_success:
            return latest_text, latest_detection
        if latest_detection.fail_count is not None and latest_detection.fail_count != 0:
            return latest_text, latest_detection
        if latest_detection.candidate_success:
            fingerprint = success_candidate_fingerprint(latest_text)
            if fingerprint and fingerprint == last_fingerprint:
                stable_reads += 1
            else:
                stable_reads = 1 if fingerprint else 0
                last_fingerprint = fingerprint
            if stable_reads >= SUCCESS_CANDIDATE_STABLE_READS and success_candidate_can_stabilize(latest_detection):
                confirmed = confirm_success_candidate(
                    latest_detection,
                    reason=f"candidate_stabilized:{latest_detection.candidate_reason or latest_detection.reason}",
                )
                return latest_text, confirmed
        else:
            stable_reads = 0
            last_fingerprint = ""
    return latest_text, latest_detection


async def detect_current_success_state(
    page: Page,
    config: WorkflowConfig,
    text: str,
    *,
    code: str = "",
) -> TemplateSuccessDetection:
    return detect_template_success(
        text,
        show_test_period_revealed=await show_test_period_revealed_on_page(page),
        thresholds=config.thresholds,
        expression=code,
    )


def success_candidate_fingerprint(text: str) -> str:
    fingerprint = result_fingerprint(text)
    if fingerprint:
        return fingerprint
    return re.sub(r"\s+", " ", (text or "").strip().lower())[:600]


def success_candidate_can_stabilize(detection: TemplateSuccessDetection) -> bool:
    strong_signals = {
        "strong_with_zero_fail",
        "average_with_zero_fail",
        "score_threshold",
        "expression_present",
    }
    return any(signal in strong_signals for signal in detection.signals)


async def fsm_quality_check(ctx: SimulateFSMContext) -> None:
    if ctx.quality is None:
        raise AutomationFlowError("[AUTOMATION] quality_parse_missing")


async def fsm_add_favorite(ctx: SimulateFSMContext) -> None:
    if not ctx.quality or not ctx.quality.passed:
        return
    correlation = check_self_correlation(
        ctx.code,
        extract_structure(ctx.code),
        metrics=ctx.metrics or {},
        enable_v2_engine=ctx.config.enable_v2_engine,
        enable_behavior_sc_pipeline=ctx.config.enable_v2_engine
        and ctx.config.enable_behavior_sc_pipeline
        and ctx.config.v2_rollout_phase >= 2,
    )
    if not correlation.passed:
        ctx.final_correlation_error = correlation.reason
        raise NonRecoverableStateError(f"[FINAL_CORRELATION] {correlation.reason}")
    ctx.screenshot = await add_to_favorites(
        page=ctx.page,
        template_file=ctx.template_file,
        alpha_name=ctx.alpha_name,
        code=ctx.code,
        metrics=ctx.metrics or {},
        quality=ctx.quality,
        correlation=correlation,
        config=ctx.config,
        platform_sc=ctx.platform_sc if isinstance(ctx.platform_sc, dict) else None,
    )


async def fsm_finished(ctx: SimulateFSMContext) -> None:
    await watchdog.browser_healthy(ctx.supervisor.browser, ctx.page)


async def fsm_recover(
    ctx: SimulateFSMContext,
    state: WorkflowState,
    policy: StatePolicy,
    exc: BaseException,
    retry: int,
) -> None:
    if policy.recovery_level == RecoveryLevel.LEVEL_1_RELOAD_PAGE:
        await ctx.page.reload(wait_until="domcontentloaded", timeout=30000)
        await restore_page_for_state_retry(ctx, state)
        return
    if policy.recovery_level == RecoveryLevel.LEVEL_2_RECREATE_PAGE:
        old_context = ctx.page.context
        try:
            await ctx.page.close()
        except Exception:
            pass
        ctx.page = await old_context.new_page()
        ctx.page.set_default_timeout(30000)
        ctx.session.page = ctx.page
        await restore_page_for_state_retry(ctx, state)
        return
    if policy.recovery_level in {RecoveryLevel.LEVEL_3_REBUILD_CONTEXT, RecoveryLevel.LEVEL_4_RESTART_BROWSER, RecoveryLevel.LEVEL_5_KILL_CHROMIUM}:
        raise AutomationFlowError(f"[AUTOMATION] recovery_requires_outer_restart:{policy.recovery_level.name}:{state.name}:{exc}")


async def restore_page_for_state_retry(ctx: SimulateFSMContext, state: WorkflowState) -> None:
    await ensure_authenticated(ctx.page, ctx.config, target_url=SIMULATE_URL)
    await wait_visible_any(ctx.page, selector_config(ctx.config, "simulate_ready", ["body"]), timeout=30000)
    await ensure_code_editor_visible(ctx.page)
    await dismiss_page_obstructions(ctx.page, f"recover_before_retry_{state.name.lower()}")

    if state in {WorkflowState.WRITE_NAME, WorkflowState.CLICK_RUN}:
        await set_editor_text(ctx.page, ctx.selectors.editor, ctx.code)
        ctx.baseline = await collect_pre_run_baseline(ctx.page)
        ctx.old_simulation_id = await read_simulation_id(ctx.page)

    if state == WorkflowState.CLICK_RUN:
        await ensure_alpha_name(ctx.page, ctx.selectors.name, ctx.alpha_name)


async def _run_platform_backtest_once(page: Page, code: str, alpha_name: str, config: WorkflowConfig) -> SimulationResult:
    editor_selectors = selector_config(
        config,
        "simulate_editor",
        ["textarea", ".monaco-editor textarea", ".cm-content", '[contenteditable="true"]', '[role="textbox"]'],
    )
    name_selectors = selector_config(
        config,
        "simulate_name",
        ['input[name="name"]', 'input[placeholder*="name" i]', 'input[aria-label*="name" i]', 'input[type="text"]'],
    )
    run_selectors = selector_config(
        config,
        "simulate_run",
        [
            'button:has-text("Run")',
            'button:has-text("Simulate")',
            '[role="button"]:has-text("Run")',
            '[role="button"]:has-text("Simulate")',
            'button:has(.editor-simulate-button-text)',
            '[role="button"]:has(.editor-simulate-button-text)',
        ],
    )

    try:
        await ensure_authenticated(page, config, target_url=SIMULATE_URL)
        await wait_visible_any(page, selector_config(config, "simulate_ready", ["body"]), timeout=30000)
        await ensure_simulate_auth(page, config, "after_initial_ready", rerun_on_reauth=False)
        await ensure_code_editor_visible(page)
        await ensure_simulate_auth(page, config, "after_editor_visible", rerun_on_reauth=False)

        await dismiss_page_obstructions(page, "before_baseline")
        baseline = await collect_pre_run_baseline(page)
        await ensure_simulate_auth(page, config, "before_editor_write")
        await set_editor_text(page, editor_selectors, code)
        await ensure_simulate_auth(page, config, "after_editor_write")
        await ensure_simulate_auth(page, config, "before_alpha_name")
        await ensure_alpha_name(page, name_selectors, alpha_name)
        await ensure_simulate_auth(page, config, "after_alpha_name")
        pre_click_progress = await read_progress(page)
        await ensure_simulate_auth(page, config, "before_run_click")
        await ensure_alpha_details_settings_not_blocking_run(page, "before_run_click")
        click_timestamp = time.time()
        simulation_session_id = f"{alpha_name}-{int(click_timestamp)}-{uuid.uuid4().hex[:8]}"
        await click_run_button(page, run_selectors)
        run_started = await ensure_run_started(page, run_selectors, baseline_progress=pre_click_progress)
        page_text = await wait_for_backtest_finished(
            page,
            config,
            baseline,
            run_started,
            baseline_progress=pre_click_progress,
            alpha_id=alpha_name,
            simulation_session_id=simulation_session_id,
        )
    except AutomationFlowError as exc:
        page_text = await safe_body_text(page)
        screenshot_path = await capture_screenshot(page, alpha_name, "automation")
        return SimulationResult(
            ok=False,
            code=code,
            alpha_name=alpha_name,
            error=PlatformError(str(exc), page_text),
            page_text=page_text,
            screenshot=screenshot_path,
        )
    except RuntimeError as exc:
        page_text = await safe_body_text(page)
        try:
            await ensure_simulate_auth(page, config, "runtime_error_auth_check", current_body=page_text)
        except AutomationFlowError as auth_exc:
            screenshot_path = await capture_screenshot(page, alpha_name, "automation")
            return SimulationResult(
                ok=False,
                code=code,
                alpha_name=alpha_name,
                error=PlatformError(str(auth_exc), page_text),
                page_text=page_text,
                screenshot=screenshot_path,
            )
        screenshot_path = await capture_screenshot(page, alpha_name, "error")
        return SimulationResult(
            ok=False,
            code=code,
            alpha_name=alpha_name,
            error=PlatformError(str(exc), page_text),
            page_text=page_text,
            screenshot=screenshot_path,
        )

    try:
        await ensure_simulate_auth(page, config, "before_result_collect")
        await ensure_alpha_details_settings_closed(page, "before_result_collect")
        page_text = await collect_result_text(page)
        await ensure_simulate_auth(page, config, "before_quality_parse", current_body=page_text)
        page_text, detection = await stabilize_success_visibility(
            page,
            config,
            page_text,
            alpha_name=alpha_name,
            code=code,
        )
        quality = parse_quality_report(page_text)
        metrics = extract_metrics(page_text)
        platform_sc = await collect_platform_sc_safely(
            page,
            alpha_name=alpha_name,
            timeout_seconds=max(1, int(getattr(config, "platform_sc_timeout_seconds", 90) or 90)),
        ) if bool(getattr(config, "enable_platform_sc_check", True)) else {"status": "skipped", "source": "platform", "reason": "disabled_by_config"}
        metrics = apply_platform_sc_to_metrics(metrics, platform_sc)
        if detection.template_success:
            emit_template_success_event(alpha_id=alpha_name, detection=detection)
        screenshot_path = await capture_screenshot(page, alpha_name, "result")
        return SimulationResult(
            ok=True,
            code=code,
            alpha_name=alpha_name,
            metrics=metrics,
            quality=quality,
            page_text=page_text,
            screenshot=screenshot_path,
            template_success=detection.template_success,
            template_success_reason=detection.reason,
            success_candidate=detection.candidate_success,
            result_uncertain=detection.result_uncertain,
            platform_sc=platform_sc,
        )
    except AutomationFlowError as exc:
        page_text = await safe_body_text(page)
        screenshot_path = await capture_screenshot(page, alpha_name, "automation")
        return SimulationResult(
            ok=False,
            code=code,
            alpha_name=alpha_name,
            error=PlatformError(str(exc), page_text),
            page_text=page_text,
            screenshot=screenshot_path,
        )


async def ensure_simulate_auth(
    page: Page,
    config: WorkflowConfig,
    stage: str,
    *,
    current_body: str | None = None,
    rerun_on_reauth: bool = True,
) -> None:
    try:
        reauthenticated = await ensure_authenticated_if_needed(
            page,
            config,
            target_url=SIMULATE_URL,
            stage=stage,
            current_body=current_body,
        )
    except RuntimeError as exc:
        raise AutomationFlowError(f"[AUTOMATION] automation_reauth_failed stage={stage}: {exc}") from exc
    if reauthenticated and rerun_on_reauth:
        raise AutomationFlowError(f"[AUTOMATION] session_expired_during_{stage}; reauth_done; rerun_current_alpha")


async def ensure_alpha_name(page: Page, selectors: list[str], alpha_name: str) -> None:
    """Write and verify the Alpha name before Run. Never continue on identity drift."""
    errors: list[str] = []

    locator, info = await find_alpha_name_locator(page, selectors)
    if not locator and await alpha_name_field_absent_is_expected(page):
        logging.info("Alpha name input is absent on the current Simulate page; skipping name write: %s", info)
        return
    if locator:
        try:
            await locator.click(timeout=3000)
            await locator.fill(alpha_name, timeout=5000)
            await commit_alpha_name_input(page)
            if await alpha_name_value_matches(locator, alpha_name):
                logging.info("Alpha name written successfully: %s", info)
                return
            errors.append("normal_fill_value_mismatch")
        except Exception as exc:
            errors.append(f"normal_fill_failed:{exc}")
    else:
        errors.append(f"normal_locate_failed:{info}")

    await close_alpha_name_obstructions(page)
    locator, info = await find_alpha_name_locator(page, selectors)
    if not locator and await alpha_name_field_absent_is_expected(page):
        logging.info("Alpha name input is still absent after closing obstructions; continuing to Run: %s", info)
        return
    if locator:
        try:
            await locator.click(timeout=3000, force=True)
            await page.keyboard.press("Control+A")
            await page.keyboard.type(alpha_name, delay=5)
            await commit_alpha_name_input(page)
            if await alpha_name_value_matches(locator, alpha_name):
                logging.info("Alpha 名称写入成功：keyboard %s", info)
                return
            errors.append("keyboard_value_mismatch")
        except Exception as exc:
            errors.append(f"keyboard_fill_failed:{exc}")
    else:
        errors.append(f"keyboard_locate_failed:{info}")

    await open_alpha_details_for_name(page)
    locator, info = await find_alpha_name_locator(page, selectors)
    if not locator and await alpha_name_field_absent_is_expected(page):
        logging.info("Alpha details name input is unavailable; continuing to Run with current page state: %s", info)
        return
    if locator:
        try:
            await locator.click(timeout=3000, force=True)
            await locator.fill(alpha_name, timeout=5000)
            await commit_alpha_name_input(page)
            if await alpha_name_value_matches(locator, alpha_name):
                logging.info("Alpha 名称写入成功：details %s", info)
                return
            errors.append("details_value_mismatch")
        except Exception as exc:
            errors.append(f"details_fill_failed:{exc}")
    else:
        errors.append(f"details_locate_failed:{info}")

    js_result = await set_alpha_name_by_js(page, alpha_name)
    if js_result.get("ok"):
        logging.info("Alpha 名称写入成功：js_fallback %s", js_result.get("reason", ""))
        return
    errors.append(f"js_fallback_failed:{js_result.get('reason', 'unknown')}")

    diagnostics = await alpha_name_failure_diagnostics(page, alpha_name)
    raise AutomationFlowError(
        "[AUTOMATION] automation_name_input_failed; alpha name input failed before Run."
        f" expected={alpha_name}; errors={' | '.join(errors)}; diagnostics={diagnostics}"
    )


async def dismiss_page_obstructions(page: Page, stage: str) -> None:
    await dismiss_cookie_banner(page)
    await ensure_alpha_details_settings_closed(page, stage)
    await dismiss_platform_toasts(page)


async def ensure_alpha_details_settings_closed(page: Page, stage: str) -> None:
    if not await alpha_details_settings_menu_visible(page):
        return
    logging.warning("检测到 Alpha Details 设置面板遮挡结果区，尝试关闭：stage=%s", stage)
    closed = await close_alpha_details_settings_menu(page, stage)
    if closed:
        return
    details = await alpha_details_settings_diagnostics(page)
    raise AutomationFlowError(f"{ALPHA_DETAILS_SETTINGS_ERROR}; stage={stage}; diagnostics={details}")


async def ensure_alpha_details_settings_not_blocking_run(page: Page, stage: str) -> None:
    if not await alpha_details_settings_menu_visible(page):
        return
    logging.warning("Detected Alpha Details settings panel before Run; trying to close it: stage=%s", stage)
    if await close_alpha_details_settings_menu(page, stage):
        return
    if not await alpha_details_settings_blocks_run_click(page):
        logging.warning("Alpha Details settings panel is still open but does not cover Run; continuing: stage=%s", stage)
        return
    details = await alpha_details_settings_diagnostics(page)
    raise AutomationFlowError(f"{ALPHA_DETAILS_SETTINGS_ERROR}; stage={stage}; diagnostics={details}")


async def try_close_alpha_details_settings_menu(page: Page, stage: str) -> bool:
    """Best-effort cleanup before a click; never interrupts passive result reading."""
    if not await alpha_details_settings_menu_visible(page):
        return True
    logging.warning("Detected Alpha Details settings panel before click; trying to close it: stage=%s", stage)
    if await close_alpha_details_settings_menu(page, stage):
        return True
    logging.warning("Alpha Details settings panel is still open; skip this click and keep waiting: stage=%s", stage)
    return False


async def alpha_details_settings_menu_visible(page: Page) -> bool:
    try:
        return bool(
            await page.evaluate(
                """() => {
                    const normalize = text => String(text || '').replace(/\\s+/g, ' ').trim();
                    const attrsOf = el => [
                        el.tagName,
                        el.id || '',
                        String(el.className || ''),
                        el.getAttribute('role') || '',
                        el.getAttribute('aria-label') || '',
                        el.getAttribute('data-testid') || ''
                    ].join(' ');
                    const visible = el => {
                        if (!el) return false;
                        const style = window.getComputedStyle(el);
                        const rect = el.getBoundingClientRect();
                        return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
                    };
                    const panelSized = el => {
                        const rect = el.getBoundingClientRect();
                        return rect.width >= 120 &&
                            rect.width <= Math.min(window.innerWidth * 0.8, 900) &&
                            rect.height >= 80 &&
                            rect.height <= window.innerHeight * 0.95 &&
                            !(rect.width >= window.innerWidth * 0.85 || rect.height >= window.innerHeight * 0.98);
                    };
                    const excludedShell = el => {
                        const cls = String(el.className || '');
                        return el.id === 'root' ||
                            /\\b(?:app-simulate|editor|editor-instance|editor-panels)\\b/i.test(cls);
                    };
                    const strictMenuText = text => {
                        if (/\\bCustomize Alpha Details Menu\\b/i.test(text)) return true;
                        return /Drag the containers to rearrange/i.test(text) &&
                            /\\bReset\\b/i.test(text) &&
                            /\\bApply\\b/i.test(text);
                    };
                    for (const el of Array.from(document.querySelectorAll('body *')).slice(0, 8000)) {
                        if (!visible(el)) continue;
                        if (excludedShell(el)) continue;
                        if (!panelSized(el)) continue;
                        const text = normalize(el.innerText || el.textContent || '');
                        if (!strictMenuText(text)) continue;
                        const attrs = attrsOf(el);
                        if (/\\bSettings\\b\\s+USA\\/D1\\/TOP3000/i.test(text) && !/\\bCustomize Alpha Details Menu\\b/i.test(text)) continue;
                        if (/\\bProperties\\b/i.test(text) && /\\bIS Summary\\b|\\bLast Run\\b|\\b\\d+\\s+(PASS|FAIL|PENDING)\\b/i.test(text) && !/\\bCustomize Alpha Details Menu\\b/i.test(text)) continue;
                        return true;
                    }
                    return false;
                }"""
            )
        )
    except Exception:
        return False


async def alpha_details_settings_blocks_run_click(page: Page) -> bool:
    try:
        return bool(
            await page.evaluate(
                """() => {
                    const normalize = text => String(text || '').replace(/\\s+/g, ' ').trim();
                    const visible = el => {
                        if (!el) return false;
                        const style = window.getComputedStyle(el);
                        const rect = el.getBoundingClientRect();
                        return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
                    };
                    const isStrictSettingsPanel = el => {
                        const text = normalize(el.innerText || el.textContent || '');
                        if (!(/\\bCustomize Alpha Details Menu\\b/i.test(text) ||
                            (/Drag the containers to rearrange/i.test(text) && /\\bReset\\b/i.test(text) && /\\bApply\\b/i.test(text)))) {
                            return false;
                        }
                        const rect = el.getBoundingClientRect();
                        const attrs = [
                            el.tagName,
                            el.id || '',
                            String(el.className || ''),
                            el.getAttribute('role') || '',
                            el.getAttribute('aria-label') || '',
                            el.getAttribute('data-testid') || ''
                        ].join(' ');
                        if (/\\b(?:app-simulate|editor|editor-instance|editor-panels)\\b/i.test(attrs) || el.id === 'root') return false;
                        return rect.width >= 120 && rect.width <= Math.min(window.innerWidth * 0.8, 900) &&
                            rect.height >= 80 && rect.height <= window.innerHeight * 0.95 &&
                            !(rect.width >= window.innerWidth * 0.85 || rect.height >= window.innerHeight * 0.98);
                    };
                    const settingsPanels = Array.from(document.querySelectorAll('body *')).filter(el => visible(el) && isStrictSettingsPanel(el));
                    if (!settingsPanels.length) return false;
                    const editor = document.querySelector('.monaco-editor, .cm-editor, .cm-content, textarea.inputarea');
                    const editorRect = editor ? editor.getBoundingClientRect() : null;
                    const candidates = [];
                    for (const raw of Array.from(document.querySelectorAll('button,[role="button"],.editor-simulate-button-text')).slice(0, 400)) {
                        if (!visible(raw)) continue;
                        const clickable = raw.closest('button,[role="button"]');
                        if (!clickable || !visible(clickable)) continue;
                        if (clickable.disabled || clickable.getAttribute('aria-disabled') === 'true') continue;
                        const text = normalize(
                            clickable.innerText || clickable.textContent ||
                            clickable.getAttribute('aria-label') || clickable.getAttribute('title') ||
                            raw.innerText || raw.textContent || ''
                        );
                        const attrs = [
                            clickable.tagName,
                            clickable.id || '',
                            String(clickable.className || ''),
                            clickable.getAttribute('role') || '',
                            clickable.getAttribute('aria-label') || '',
                            clickable.getAttribute('title') || '',
                            clickable.getAttribute('data-testid') || '',
                            raw.id || '',
                            String(raw.className || '')
                        ].join(' ');
                        if (/submit/i.test(text + ' ' + attrs)) continue;
                        const runish = /^(run|simulate|运行|模拟)$/i.test(text) || /editor-simulate-button-text|simulate|run/i.test(attrs);
                        if (!runish) continue;
                        const rect = clickable.getBoundingClientRect();
                        let score = 0;
                        if (/^(run|simulate|运行|模拟)$/i.test(text)) score += 20;
                        if (/editor-simulate-button-text|simulate/i.test(attrs)) score += 25;
                        if (editorRect) {
                            const verticalNearEditor = rect.top >= editorRect.top - 140 && rect.top <= editorRect.bottom + 180;
                            const horizontalNearEditor = rect.left >= editorRect.left - 80 && rect.left <= editorRect.right + 260;
                            if (verticalNearEditor && horizontalNearEditor) score += 40;
                        }
                        if (rect.top < 120 || rect.left < 120) score -= 20;
                        candidates.push({el: clickable, score});
                    }
                    candidates.sort((a, b) => b.score - a.score);
                    const best = candidates[0];
                    if (!best || best.score < 20) return true;
                    const rect = best.el.getBoundingClientRect();
                    const points = [
                        [rect.left + rect.width / 2, rect.top + rect.height / 2],
                        [rect.left + Math.min(rect.width - 1, 12), rect.top + Math.min(rect.height - 1, 12)]
                    ];
                    for (const [x, y] of points) {
                        const top = document.elementFromPoint(
                            Math.max(1, Math.min(window.innerWidth - 1, x)),
                            Math.max(1, Math.min(window.innerHeight - 1, y))
                        );
                        if (!top) continue;
                        if (top === best.el || best.el.contains(top) || top.contains(best.el)) continue;
                        if (settingsPanels.some(panel => panel === top || panel.contains(top))) return true;
                    }
                    return false;
                }"""
            )
        )
    except Exception:
        return True


async def close_alpha_details_settings_menu(page: Page, stage: str) -> bool:
    was_visible = await alpha_details_settings_menu_visible(page)
    if not was_visible:
        return True
    try:
        await page.keyboard.press("Escape")
        await asyncio.sleep(0.4)
    except Exception:
        pass
    if not await alpha_details_settings_menu_visible(page):
        logging.info("Closed Alpha Details settings panel with Escape: stage=%s", stage)
        return True
    try:
        await page.mouse.click(1018, 180)
        await asyncio.sleep(0.4)
    except Exception:
        pass
    if not await alpha_details_settings_menu_visible(page):
        logging.info("Closed Alpha Details settings panel by clicking result whitespace: stage=%s", stage)
        return True
    try:
        toggled = await page.evaluate(
            """() => {
                const normalize = text => String(text || '').replace(/\\s+/g, ' ').trim();
                const visible = el => {
                    if (!el) return false;
                    const style = window.getComputedStyle(el);
                    const rect = el.getBoundingClientRect();
                    return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
                };
                const controls = Array.from(document.querySelectorAll('button,[role="button"]')).filter(visible);
                for (const control of controls) {
                    const text = normalize(control.innerText || control.textContent || control.getAttribute('aria-label') || control.getAttribute('title') || '');
                    const attrs = [
                        control.tagName,
                        control.id || '',
                        String(control.className || ''),
                        control.getAttribute('role') || '',
                        control.getAttribute('aria-label') || '',
                        control.getAttribute('title') || ''
                    ].join(' ');
                    if (!/alphas-details__action-settings/i.test(attrs)) continue;
                    if (/Submit|Apply|Reset/i.test(text)) continue;
                    const cls = String(control.className || '');
                    if (/\\b(?:app-simulate|editor|editor-instance|editor-panels)\\b/i.test(cls)) continue;
                    control.dispatchEvent(new MouseEvent('mousedown', {bubbles: true, cancelable: true}));
                    control.dispatchEvent(new MouseEvent('mouseup', {bubbles: true, cancelable: true}));
                    control.click();
                    return true;
                }
                return false;
            }"""
        )
        if toggled:
            await asyncio.sleep(0.5)
    except Exception:
        pass
    if not await alpha_details_settings_menu_visible(page):
        logging.info("已通过 Escape 关闭 Alpha Details 设置面板：stage=%s", stage)
        return True
    return False


async def alpha_details_settings_diagnostics(page: Page) -> str:
    try:
        data = await page.evaluate(
            """() => {
                const normalize = text => String(text || '').replace(/\\s+/g, ' ').trim();
                const attrsOf = el => [
                    el.tagName,
                    el.id || '',
                    String(el.className || ''),
                    el.getAttribute('role') || '',
                    el.getAttribute('aria-label') || '',
                    el.getAttribute('data-testid') || ''
                ].join(' ');
                const visible = el => {
                    if (!el) return false;
                    const style = window.getComputedStyle(el);
                    const rect = el.getBoundingClientRect();
                    return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
                };
                const panelSized = el => {
                    const rect = el.getBoundingClientRect();
                    return rect.width >= 120 &&
                        rect.width <= Math.min(window.innerWidth * 0.8, 900) &&
                        rect.height >= 80 &&
                        rect.height <= window.innerHeight * 0.95 &&
                        !(rect.width >= window.innerWidth * 0.85 || rect.height >= window.innerHeight * 0.98);
                };
                const excludedShell = el => {
                    const cls = String(el.className || '');
                    return el.id === 'root' ||
                        /\\b(?:app-simulate|editor|editor-instance|editor-panels)\\b/i.test(cls);
                };
                const strictReason = text => {
                    if (/\\bCustomize Alpha Details Menu\\b/i.test(text)) return 'title';
                    if (/Drag the containers to rearrange/i.test(text) && /\\bReset\\b/i.test(text) && /\\bApply\\b/i.test(text)) return 'drag-reset-apply';
                    return '';
                };
                const selectorFor = el => {
                    const parts = [];
                    let node = el;
                    for (let depth = 0; node && node.nodeType === 1 && depth < 5; depth += 1, node = node.parentElement) {
                        let part = node.tagName.toLowerCase();
                        if (node.id) part += '#' + node.id;
                        const classes = String(node.className || '').split(/\\s+/).filter(Boolean).slice(0, 3);
                        if (classes.length) part += '.' + classes.join('.');
                        parts.unshift(part);
                    }
                    return parts.join(' > ');
                };
                const strict = [];
                const secondary = [];
                for (const el of Array.from(document.querySelectorAll('body *')).slice(0, 8000)) {
                    if (!visible(el)) continue;
                    const text = normalize(el.innerText || el.textContent || '');
                    const attrs = attrsOf(el);
                    const reason = strictReason(text);
                    const rect = el.getBoundingClientRect();
                    if (reason && panelSized(el) && !excludedShell(el)) {
                        const ancestors = [];
                        let node = el.parentElement;
                        for (let depth = 0; node && depth < 5; depth += 1, node = node.parentElement) {
                            ancestors.push({selector: selectorFor(node), attrs: attrsOf(node).slice(0, 220)});
                        }
                        strict.push({
                            reason,
                            selector: selectorFor(el),
                            text: text.slice(0, 260),
                            attrs: attrs.slice(0, 260),
                            rect: {x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height)},
                            ancestors
                        });
                    } else if (/settings-sortable|settings-content|settings-actions|alphas-details__action-settings/i.test(attrs) || /Customize Alpha Details Menu|Drag the containers|Reset\\s+Apply/i.test(text)) {
                        secondary.push({text: text.slice(0, 180), attrs: attrs.slice(0, 220), rect: {x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height)}});
                    }
                }
                return {strict: strict.slice(0, 4), secondary: secondary.slice(0, 6)};
            }"""
        )
        return re.sub(r"\s+", " ", json.dumps(data, ensure_ascii=False))[:1600]
    except Exception as exc:
        return f"diagnostics_failed:{exc}"


async def find_alpha_name_locator(page: Page, selectors: list[str]):
    ordered = list(
        dict.fromkeys(
            selectors
            + [
                'input[name="name"]',
                'input[name*="name" i]',
                'input[placeholder*="alpha" i]',
                'input[placeholder*="name" i]',
                'input[aria-label*="alpha" i]',
                'input[aria-label*="name" i]',
                'input[data-testid*="name" i]',
                'input[id*="name" i]',
                'input[type="text"]',
            ]
        )
    )
    candidates: list[tuple[int, int, Any, str]] = []
    sequence = 0
    for selector in ordered:
        try:
            locator_group = page.locator(selector)
            count = min(await locator_group.count(), 30)
        except Exception:
            continue
        for index in range(count):
            locator = locator_group.nth(index)
            try:
                if not await locator.is_visible(timeout=300):
                    continue
                info = await score_alpha_name_candidate(locator)
                score = int(info.get("score", 0))
                if score < 45:
                    continue
                sequence += 1
                candidates.append((score, -sequence, locator, f"{selector}[{index}] score={score} reason={info.get('reason', '')}"))
            except Exception:
                continue
    if not candidates:
        return None, "no editable alpha name candidate"
    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    _, _, locator, info = candidates[0]
    return locator, info


async def alpha_name_field_absent_is_expected(page: Page) -> bool:
    try:
        return bool(
            await page.evaluate(
                """() => {
                    const normalize = text => String(text || '').replace(/\\s+/g, ' ').trim();
                    const visible = el => {
                        if (!el) return false;
                        const style = window.getComputedStyle(el);
                        const rect = el.getBoundingClientRect();
                        return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
                    };
                    const editableNameInputs = Array.from(document.querySelectorAll('input,textarea')).filter(el => {
                        const tag = String(el.tagName || '').toLowerCase();
                        const type = String(el.getAttribute('type') || '').toLowerCase();
                        if (!visible(el) || el.disabled || el.readOnly || el.getAttribute('aria-disabled') === 'true') return false;
                        if (tag === 'textarea' && /monaco|cm-editor|code|expression/i.test(String(el.className || '') + ' ' + (el.getAttribute('aria-label') || ''))) return false;
                        if (/hidden|password|checkbox|radio|file|submit|button|range|number|date/.test(type)) return false;
                        const attrs = [
                            el.id || '',
                            String(el.className || ''),
                            el.getAttribute('name') || '',
                            el.getAttribute('placeholder') || '',
                            el.getAttribute('aria-label') || '',
                            el.getAttribute('data-testid') || ''
                        ].join(' ');
                        return /\\balpha\\b|\\bname\\b|title/i.test(attrs);
                    });
                    if (editableNameInputs.length > 0) return false;
                    const body = normalize(document.body ? document.body.innerText || document.body.textContent || '' : '');
                    const hasEditor = Boolean(document.querySelector('.monaco-editor, .cm-editor, .cm-content, textarea.inputarea'));
                    const simulateWorkspace = /\\bCODE\\b|\\bRESULTS\\b|\\bLEARN\\b|\\bDATA\\b|\\bSimulate\\b/i.test(body);
                    return hasEditor && simulateWorkspace;
                }"""
            )
        )
    except Exception:
        return False


async def score_alpha_name_candidate(locator) -> dict:
    return await locator.evaluate(
        """el => {
            const normalize = text => String(text || '').replace(/\\s+/g, ' ').trim();
            const style = window.getComputedStyle(el);
            const rect = el.getBoundingClientRect();
            const visible = style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
            const tag = String(el.tagName || '').toLowerCase();
            const type = String(el.getAttribute('type') || '').toLowerCase();
            const attrs = [
                tag,
                type,
                el.id || '',
                String(el.className || ''),
                el.getAttribute('name') || '',
                el.getAttribute('placeholder') || '',
                el.getAttribute('aria-label') || '',
                el.getAttribute('data-testid') || '',
                el.getAttribute('autocomplete') || ''
            ].join(' ');
            let parentText = '';
            let parentAttrs = '';
            let node = el;
            for (let depth = 0; node && depth < 7; depth += 1, node = node.parentElement) {
                parentText += ' ' + normalize(node.innerText || node.textContent || '').slice(0, 300);
                parentAttrs += ' ' + [
                    node.tagName,
                    node.id || '',
                    String(node.className || ''),
                    node.getAttribute('role') || '',
                    node.getAttribute('aria-label') || '',
                    node.getAttribute('data-testid') || ''
                ].join(' ');
            }
            const hay = `${attrs} ${parentText} ${parentAttrs}`;
            let score = 0;
            const reasons = [];
            if (!visible) return {score: -100, reason: 'hidden'};
            if (tag !== 'input' && tag !== 'textarea') return {score: -100, reason: 'not_input'};
            if (/hidden|password|checkbox|radio|file|submit|button|range|number|date/.test(type)) return {score: -100, reason: 'bad_type'};
            if (el.disabled || el.readOnly || el.getAttribute('aria-disabled') === 'true') return {score: -100, reason: 'disabled_or_readonly'};
            if (/\\bsearch\\b|filter|query|lookup|datafield|dataset|operator/.test(hay)) {
                score -= 70; reasons.push('search_or_filter');
            }
            if (/monaco|cm-editor|code|expression|fast expression|textarea\\.inputarea/.test(hay)) {
                score -= 90; reasons.push('editor');
            }
            if (/nav|navigation|sidebar|topbar|navbar|header/.test(parentAttrs) && rect.top < 220) {
                score -= 70; reasons.push('navigation');
            }
            if (/\\balpha\\b/i.test(hay)) { score += 24; reasons.push('alpha'); }
            if (/\\bname\\b|title/i.test(attrs)) { score += 42; reasons.push('name_attr'); }
            if (/\\bname\\b|title/i.test(parentText)) { score += 22; reasons.push('name_parent'); }
            if (/properties|details|setting|description|summary|alpha-detail/i.test(hay)) { score += 18; reasons.push('details_region'); }
            if (type === 'text' || !type) { score += 8; reasons.push('text_input'); }
            if (rect.width >= 120 && rect.height >= 20) { score += 8; reasons.push('reasonable_size'); }
            if (String(el.value || '').length <= 160) { score += 5; reasons.push('short_value'); }
            return {
                score,
                reason: reasons.join(','),
                value: String(el.value || '').slice(0, 200),
                attrs: attrs.slice(0, 300),
                parentText: normalize(parentText).slice(0, 500),
                rect: {x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height)}
            };
        }"""
    )


async def alpha_name_value_matches(locator, expected: str) -> bool:
    try:
        value = await locator.evaluate("el => String(el.value || el.textContent || '').trim()")
        return normalize_alpha_name(value) == normalize_alpha_name(expected)
    except Exception:
        return False


def normalize_alpha_name(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


async def commit_alpha_name_input(page: Page) -> None:
    try:
        await page.keyboard.press("Tab")
    except Exception:
        pass
    await asyncio.sleep(0.4)


async def close_alpha_name_obstructions(page: Page) -> None:
    try:
        await page.keyboard.press("Escape")
        await asyncio.sleep(0.3)
    except Exception:
        pass
    selectors = [
        '[role="dialog"] button[aria-label*="close" i]',
        '[role="menu"] button[aria-label*="close" i]',
        '[class*="modal" i] button[aria-label*="close" i]',
        '[class*="popover" i] button[aria-label*="close" i]',
        'button:has-text("Cancel")',
    ]
    for selector in selectors:
        try:
            button = page.locator(selector).first
            if await button.is_visible(timeout=300):
                text = await button.inner_text(timeout=300)
                if re.search(r"\bSubmit\b|提交", text, re.I):
                    continue
                await button.click(timeout=800, force=True)
                await asyncio.sleep(0.2)
        except Exception:
            continue


async def open_alpha_details_for_name(page: Page) -> None:
    await close_alpha_details_settings_menu(page, "before_open_alpha_details_for_name")
    selectors = [
        'button.alphas-details__actions-item--properties',
        'button:has-text("Properties")',
        '[role="button"]:has-text("Properties")',
        'button[aria-label*="Properties" i]',
    ]
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            if not await locator.is_visible(timeout=400):
                continue
            text = await locator.inner_text(timeout=400)
            if re.search(r"\bSubmit\b|提交", text, re.I):
                continue
            if not await is_result_region_control(locator):
                continue
            await locator.click(timeout=1200, force=True)
            await asyncio.sleep(0.7)
            await close_alpha_details_settings_menu(page, "after_open_alpha_details_for_name")
            return
        except Exception:
            continue


async def set_alpha_name_by_js(page: Page, alpha_name: str) -> dict:
    try:
        return dict(
            await page.evaluate(
                """expected => {
                    const normalize = text => String(text || '').replace(/\\s+/g, ' ').trim();
                    const visible = el => {
                        if (!el) return false;
                        const style = window.getComputedStyle(el);
                        const rect = el.getBoundingClientRect();
                        return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
                    };
                    const score = el => {
                        const tag = String(el.tagName || '').toLowerCase();
                        const type = String(el.getAttribute('type') || '').toLowerCase();
                        if (!visible(el) || tag !== 'input' || /hidden|password|checkbox|radio|file|submit|button/.test(type)) return -100;
                        if (el.disabled || el.readOnly || el.getAttribute('aria-disabled') === 'true') return -100;
                        const attrs = [
                            el.id || '',
                            String(el.className || ''),
                            el.getAttribute('name') || '',
                            el.getAttribute('placeholder') || '',
                            el.getAttribute('aria-label') || '',
                            el.getAttribute('data-testid') || ''
                        ].join(' ');
                        let parentText = '';
                        let node = el;
                        for (let depth = 0; node && depth < 6; depth += 1, node = node.parentElement) {
                            parentText += ' ' + normalize(node.innerText || node.textContent || '').slice(0, 220);
                        }
                        const hay = `${attrs} ${parentText}`;
                        let value = 0;
                        if (/search|filter|query|monaco|cm-editor|code|expression/i.test(hay)) value -= 90;
                        if (/alpha/i.test(hay)) value += 24;
                        if (/\\bname\\b|title/i.test(attrs)) value += 42;
                        if (/\\bname\\b|title/i.test(parentText)) value += 22;
                        if (/properties|details|setting|alpha-detail/i.test(hay)) value += 18;
                        return value;
                    };
                    const inputs = Array.from(document.querySelectorAll('input,textarea'))
                        .map(el => ({el, score: score(el)}))
                        .filter(item => item.score >= 45)
                        .sort((a, b) => b.score - a.score);
                    const best = inputs[0];
                    if (!best) return {ok: false, reason: 'no_candidate'};
                    const el = best.el;
                    el.focus();
                    const setter = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(el), 'value')?.set;
                    if (setter) setter.call(el, expected); else el.value = expected;
                    el.dispatchEvent(new InputEvent('input', {bubbles: true, inputType: 'insertText', data: expected}));
                    el.dispatchEvent(new Event('change', {bubbles: true}));
                    el.dispatchEvent(new FocusEvent('blur', {bubbles: true}));
                    const ok = normalize(el.value) === normalize(expected);
                    return {ok, reason: `score=${best.score} value=${String(el.value || '').slice(0, 120)}`};
                }""",
                alpha_name,
            )
        )
    except Exception as exc:
        return {"ok": False, "reason": str(exc)}


async def alpha_name_failure_diagnostics(page: Page, expected: str) -> str:
    try:
        data = await page.evaluate(
            """expected => {
                const normalize = text => String(text || '').replace(/\\s+/g, ' ').trim();
                const visible = el => {
                    const style = window.getComputedStyle(el);
                    const rect = el.getBoundingClientRect();
                    return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
                };
                const inputs = Array.from(document.querySelectorAll('input,textarea')).slice(0, 80).map(el => {
                    const rect = el.getBoundingClientRect();
                    let parentText = '';
                    let node = el;
                    for (let depth = 0; node && depth < 4; depth += 1, node = node.parentElement) {
                        parentText += ' ' + normalize(node.innerText || node.textContent || '').slice(0, 180);
                    }
                    return {
                        tag: el.tagName,
                        type: el.getAttribute('type') || '',
                        name: el.getAttribute('name') || '',
                        placeholder: el.getAttribute('placeholder') || '',
                        aria: el.getAttribute('aria-label') || '',
                        testid: el.getAttribute('data-testid') || '',
                        value: String(el.value || '').slice(0, 120),
                        visible: visible(el),
                        disabled: Boolean(el.disabled || el.getAttribute('aria-disabled') === 'true'),
                        readonly: Boolean(el.readOnly),
                        rect: {x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height)},
                        parentText: normalize(parentText).slice(0, 220)
                    };
                });
                return {expected, inputCount: inputs.length, visibleInputCount: inputs.filter(x => x.visible).length, inputs: inputs.slice(0, 12)};
            }""",
            expected,
        )
        return re.sub(r"\s+", " ", json.dumps(data, ensure_ascii=False))[:1600]
    except Exception as exc:
        return f"diagnostics_failed:{exc}"


async def click_run_button(page: Page, run_selectors: list[str]) -> None:
    clicked = await click_run_button_by_dom(page)
    if clicked:
        logging.info("网页点击：Run selector=%s", clicked)
        return
    logging.warning("Run control not found by DOM-specific logic; using configured selector fallback")
    await safe_click(page, run_selectors, "Run")


async def click_run_button_by_dom(page: Page) -> str:
    try:
        candidate = await page.evaluate(
            """() => {
                const normalize = text => String(text || '').replace(/\\s+/g, ' ').trim();
                const visible = el => {
                    if (!el) return false;
                    const style = window.getComputedStyle(el);
                    const rect = el.getBoundingClientRect();
                    return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
                };
                const inGlobalNavigation = el => {
                    let node = el;
                    for (let depth = 0; node && depth < 8; depth += 1, node = node.parentElement) {
                        const attrs = [
                            node.tagName,
                            node.id || '',
                            String(node.className || ''),
                            node.getAttribute('role') || '',
                            node.getAttribute('aria-label') || '',
                            node.getAttribute('data-testid') || ''
                        ].join(' ');
                        if (/\\b(nav|navigation|sidebar|side-bar|menu|topbar|navbar|header)\\b/i.test(attrs)) return true;
                    }
                    return false;
                };
                const editor = document.querySelector('.monaco-editor, .cm-editor, .cm-content, textarea.inputarea');
                const editorRect = editor ? editor.getBoundingClientRect() : null;
                const candidates = [];
                for (const raw of Array.from(document.querySelectorAll('button,[role="button"],.editor-simulate-button-text')).slice(0, 400)) {
                    if (!visible(raw)) continue;
                    const clickable = raw.closest('button,[role="button"]');
                    if (!clickable || !visible(clickable)) continue;
                    if (!visible(clickable)) continue;
                    if (clickable.disabled || clickable.getAttribute('aria-disabled') === 'true') continue;
                    if (inGlobalNavigation(clickable)) continue;
                    const text = normalize(
                        clickable.innerText || clickable.textContent ||
                        clickable.getAttribute('aria-label') || clickable.getAttribute('title') ||
                        raw.innerText || raw.textContent || ''
                    );
                    const attrs = [
                        clickable.tagName,
                        clickable.id || '',
                        String(clickable.className || ''),
                        clickable.getAttribute('role') || '',
                        clickable.getAttribute('aria-label') || '',
                        clickable.getAttribute('title') || '',
                        clickable.getAttribute('data-testid') || '',
                        raw.id || '',
                        String(raw.className || '')
                    ].join(' ');
                    if (/submit/i.test(text + ' ' + attrs)) continue;
                    const runish = /^(run|simulate|运行|模拟)$/i.test(text) || /editor-simulate-button-text|simulate|run/i.test(attrs);
                    if (!runish) continue;
                    const rect = clickable.getBoundingClientRect();
                    let score = 0;
                    if (/^(run|simulate|运行|模拟)$/i.test(text)) score += 20;
                    if (/editor-simulate-button-text|simulate/i.test(attrs)) score += 25;
                    if (editorRect) {
                        const verticalNearEditor = rect.top >= editorRect.top - 140 && rect.top <= editorRect.bottom + 180;
                        const horizontalNearEditor = rect.left >= editorRect.left - 80 && rect.left <= editorRect.right + 260;
                        if (verticalNearEditor && horizontalNearEditor) score += 40;
                    }
                    if (rect.top < 120 || rect.left < 120) score -= 20;
                    candidates.push({clickable, text, attrs, score});
                }
                candidates.sort((a, b) => b.score - a.score);
                const best = candidates[0];
                if (!best || best.score < 20) {
                    return null;
                }
                best.clickable.scrollIntoView({block: 'center', inline: 'center'});
                const rect = best.clickable.getBoundingClientRect();
                const x = Math.max(1, Math.min(window.innerWidth - 1, rect.left + rect.width / 2));
                const y = Math.max(1, Math.min(window.innerHeight - 1, rect.top + rect.height / 2));
                const top = document.elementFromPoint(x, y);
                const covered = Boolean(top && !(top === best.clickable || best.clickable.contains(top) || top.contains(best.clickable)));
                return {
                    text: best.text || 'icon',
                    score: best.score,
                    attrs: best.attrs.slice(0, 160),
                    x,
                    y,
                    covered,
                    top: top ? normalize(`${top.tagName || ''} ${top.id || ''} ${String(top.className || '')}`) : ''
                };
            }"""
        )
    except Exception:
        return ""
    if not isinstance(candidate, dict):
        return ""
    try:
        x = float(candidate.get("x") or 0)
        y = float(candidate.get("y") or 0)
    except (TypeError, ValueError):
        return ""
    if x <= 0 or y <= 0:
        return ""
    if candidate.get("covered"):
        logging.warning("Run candidate appears covered before click: top=%s", str(candidate.get("top") or "")[:120])
    try:
        await page.mouse.click(x, y)
        await page.wait_for_timeout(300)
    except Exception as exc:
        logging.warning("Playwright mouse click on Run candidate failed: %s", exc)
        return ""
    return (
        f"{candidate.get('text') or 'icon'} score={candidate.get('score')} "
        f"x={x:.1f} y={y:.1f} attrs={str(candidate.get('attrs') or '')}"
    )


async def ensure_run_started(page: Page, run_selectors: list[str], baseline_progress: float | None = None) -> bool:
    if await run_start_signal_seen(page, timeout_seconds=12, baseline_progress=baseline_progress):
        return True
    logging.warning("点击 Run 后未观察到新回测启动迹象，尝试再次点击 Simulate/Run")
    await dismiss_platform_toasts(page)
    try:
        await ensure_alpha_details_settings_not_blocking_run(page, "before_run_retry_click")
        await click_run_button(page, run_selectors)
    except Exception as exc:
        logging.warning("Run retry click failed: %s", exc)
        return False
    if not await run_start_signal_seen(page, timeout_seconds=12, baseline_progress=baseline_progress):
        logging.warning("Run 重试后仍未观察到进度条或运行状态，后续等待会防止误读旧结果")
        return False
    return True


async def run_start_signal_seen(page: Page, timeout_seconds: int, baseline_progress: float | None = None) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        progress = await read_progress(page)
        if progress is not None and progress <= 99.9 and progress_changed_from_baseline(progress, baseline_progress):
            logging.info("已观察到新回测启动迹象：progress=%.1f%%", progress)
            return True
        text = await safe_body_text(page, timeout=3000)
        if re.search(r"running|simulating|queued|loading|calculating|in progress|Simulations usually take|cancel the simulation|Saving\.\.\.", text, re.I):
            logging.info("已观察到新回测启动迹象：页面运行文案")
            return True
        if await simulate_run_loading_indicator(page):
            logging.info("已观察到新回测启动迹象：加载/进度控件")
            return True
        await asyncio.sleep(1.5)
    return False


def progress_changed_from_baseline(progress: float, baseline_progress: float | None) -> bool:
    if baseline_progress is None:
        return True
    return abs(progress - baseline_progress) >= 0.1


async def collect_pre_run_baseline(page: Page) -> str:
    """Read a slightly stabilized pre-run page snapshot so stale results are fingerprinted."""
    pieces: list[str] = []
    for delay in [0.0, 1.0, 1.5]:
        if delay:
            await asyncio.sleep(delay)
        text = await safe_body_text(page, timeout=3000)
        if text.strip():
            pieces.append(text)
    combined = "\n".join(dedupe_plain_messages(pieces))
    fingerprint = result_fingerprint(combined)
    if fingerprint:
        logging.info("Detected pre-run stale result fingerprint for IS guard: %s", fingerprint[:180])
    return combined


async def wait_for_backtest_finished(
    page: Page,
    config: WorkflowConfig,
    baseline_text: str,
    observed_start: bool,
    *,
    baseline_progress: float | None = None,
    alpha_id: str = "",
    simulation_session_id: str = "",
) -> str:
    max_wait = wait_result_max_seconds(config)
    deadline = time.time() + max_wait
    started = time.time()
    saw_running = False
    saw_progress_100 = False
    stable_count = 0
    stable_candidate_started_at: float | None = None
    last_stable_fingerprint = ""
    max_progress: float = 0.0
    last_progress: float | None = None
    last_progress_change_at = started
    last_wait_log_at = started
    baseline_result_fingerprint = result_fingerprint(baseline_text)
    baseline_had_result_shell = looks_like_concrete_backtest_result(baseline_text)
    baseline_error_fingerprint = error_fingerprint(extract_error_lines_from_text(baseline_text))
    show_test_period_revealed = False

    while time.time() < deadline:
        now = time.time()
        progress = await read_progress(page)
        if progress is not None:
            max_progress = max(max_progress, progress)
            if last_progress is None or abs(progress - last_progress) >= 0.1:
                logging.info("Platform backtest progress: %.1f%%", progress)
                last_progress = progress
                last_progress_change_at = time.time()
            if progress < 99.9 and progress_changed_from_baseline(progress, baseline_progress):
                saw_running = True
            if progress >= 100:
                saw_progress_100 = True

        focused_text = await collect_focused_result_text(page)
        text = focused_text or await safe_body_text(page)
        await ensure_simulate_auth(page, config, "backtest_wait", current_body=text)
        if re.search(r"running|simulating|queued|loading|calculating|in progress", text, re.I):
            saw_running = True

        elapsed = time.time() - started
        if not saw_running and not observed_start and elapsed >= wait_result_start_timeout_seconds(config):
            raise AutomationFlowError("[AUTOMATION] run_submission_not_confirmed: simulation did not start within WAIT_RESULT phase A")
        progress_active = progress is not None and progress < 99.9
        visible_result_shell = await result_shell_visible(page)
        has_result_shell = looks_like_result_shell_text(focused_text) or visible_result_shell
        has_concrete_result = has_result_shell and looks_like_concrete_backtest_result(focused_text or text)
        new_result_seen = has_new_result(focused_text or text, baseline_result_fingerprint)
        current_result_fingerprint = result_fingerprint(focused_text or text)
        stable_fingerprint = stable_result_fingerprint(focused_text or text)

        should_try_reveal = bool(
            not progress_active
            and (
                await show_test_period_button_visible(page)
                or progress is not None and progress >= 99.9
                or saw_progress_100
                or has_result_shell
                or has_concrete_result
            )
        )
        if should_try_reveal:
            if not show_test_period_revealed:
                show_test_period_revealed = await detect_and_click_show_test_period(page)
            await reveal_result_panels(page, include_show_test_period=False)
            focused_text = await collect_focused_result_text(page)
            text = focused_text or await safe_body_text(page)
            await ensure_simulate_auth(page, config, "backtest_wait_after_reveal", current_body=text)
            has_result_shell = looks_like_result_shell_text(focused_text) or await result_shell_visible(page)
            has_concrete_result = has_result_shell and looks_like_concrete_backtest_result(focused_text or text)
            new_result_seen = has_new_result(focused_text or text, baseline_result_fingerprint)
            current_result_fingerprint = result_fingerprint(focused_text or text)
            stable_fingerprint = stable_result_fingerprint(focused_text or text)

        errors = await detect_platform_errors(page, baseline_error_fingerprint=baseline_error_fingerprint)
        if errors:
            raise NonRecoverableStateError(errors)

        if time.time() - last_wait_log_at >= 60:
            logging.info(
                "等待平台回测结果：elapsed=%ss progress=%s max_progress=%.1f%% result_shell=%s concrete_result=%s new_result=%s",
                int(elapsed),
                f"{progress:.1f}%" if progress is not None else "none",
                max_progress,
                has_result_shell,
                has_concrete_result,
                new_result_seen,
            )
            last_wait_log_at = time.time()

        ready_for_current_result = False
        ready_reason = ""
        if has_concrete_result:
            ready_for_current_result, ready_reason = result_ready_for_current_run(
                current_text=focused_text or text,
                baseline_fingerprint=baseline_result_fingerprint,
                baseline_had_result_shell=baseline_had_result_shell,
                observed_start=observed_start or saw_running,
                max_progress=max_progress,
                elapsed=elapsed,
            )
        progress_complete = bool(progress is not None and progress >= 99.9) or saw_progress_100
        progress_disappeared_with_ready_result = bool(progress is None and ready_for_current_result)
        stable_completion_candidate = progress_complete or progress_disappeared_with_ready_result
        if stable_completion_candidate and has_concrete_result and stable_fingerprint:
            if stable_fingerprint == last_stable_fingerprint:
                stable_count += 1
            else:
                stable_count = 1
                last_stable_fingerprint = stable_fingerprint
                stable_candidate_started_at = now
            stable_window_elapsed = now - stable_candidate_started_at if stable_candidate_started_at else 0.0
            if alpha_id:
                log_state_event(
                    STATE_PROGRESS,
                    alpha_id=alpha_id,
                    state=WorkflowState.WAIT_RESULT.name,
                    extra={
                        "simulation_session_id": simulation_session_id,
                        "result_fingerprint": stable_fingerprint,
                        "result_stable_count": stable_count,
                        "stable_window": round(stable_window_elapsed, 3),
                        "metrics_stable": stable_count >= result_stable_reads(config),
                    },
                )
            if stable_count >= result_stable_reads(config) and stable_window_elapsed >= result_dom_stable_window_seconds(config):
                ready, reason = ready_for_current_result, ready_reason
                if ready:
                    await reveal_result_panels(page, include_show_test_period=False)
                    text = await read_result_or_body_text(page)
                    logging.info(
                        "平台回测完成并通过稳定窗口：%s；stable_count=%s stable_window=%.1fs feature=%s",
                        reason,
                        stable_count,
                        stable_window_elapsed,
                        await result_feature_summary(page, text),
                    )
                    return text
            if stable_count < result_stable_reads(config) or stable_window_elapsed < result_dom_stable_window_seconds(config):
                await asyncio.sleep(result_poll_interval_seconds(config))
                continue
        elif stable_completion_candidate:
            stable_count = 0
            last_stable_fingerprint = ""
            stable_candidate_started_at = None

        recent_progress_active = (
            last_progress is not None
            and not saw_progress_100
            and time.time() - last_progress_change_at < 180
        )

        # 结果特征元素一旦出现，就优先读取。平台有时会在结果已生成后仍保留 20% 进度条，
        # 因此这里不能先被“仍在运行”的判断挡住。
        if has_result_shell and (has_concrete_result or not progress_active):
            ready, reason = result_ready_for_current_run(
                current_text=focused_text or text,
                baseline_fingerprint=baseline_result_fingerprint,
                baseline_had_result_shell=baseline_had_result_shell,
                observed_start=observed_start,
                max_progress=max_progress,
                elapsed=elapsed,
            )
            if (
                not config.enable_result_consistency_validation
                and has_concrete_result
                and elapsed >= 5
                and ready
            ):
                await reveal_result_panels(page, include_show_test_period=False)
                text = await read_result_or_body_text(page)
                logging.info("平台回测完成，判定为本轮新结果：%s；特征：%s", reason, await result_feature_summary(page, text))
                return text
            if not has_concrete_result:
                    await reveal_result_panels(page, include_show_test_period=False)
                    logging.info("Result region visible but concrete IS Summary / IS Testing Status is still loading")
            elif elapsed >= 30:
                if (progress is not None and progress >= 15) or recent_progress_active:
                    logging.info(
                        "已进入平台回测阶段但当前结果未通过本轮判定链：%s；current_fp=%s baseline_fp=%s",
                        reason,
                        current_result_fingerprint[:160],
                        baseline_result_fingerprint[:160],
                    )
                else:
                    if elapsed >= 75:
                        raise AutomationFlowError("[AUTOMATION] 点击 Run 后未触发新的可确认回测结果，页面仍显示旧结果；这是网页自动化或平台未接受运行请求的问题，不应交给 DeepSeek 修改代码")
                    logging.warning("页面仍显示旧回测结果，尚未观察到新的运行进度或结果变化，继续等待")

        running_text_active = bool(re.search(r"Simulations usually take|cancel the simulation|Saving\.\.\.|Loading|Calculating", text, re.I))
        loading_indicator_active = await simulate_run_loading_indicator(page)
        active_reasons = [
            name
            for name, active in [
                ("progress_below_100", progress_active),
                ("recent_progress_change", recent_progress_active),
                ("running_text", running_text_active),
                ("loading_indicator", loading_indicator_active),
            ]
            if active
        ]
        actively_running = bool(active_reasons)
        if actively_running:
            await asyncio.sleep(3)
            continue

        if not config.enable_result_consistency_validation and has_concrete_result and elapsed >= 5:
            ready, reason = result_ready_for_current_run(
                current_text=focused_text or text,
                baseline_fingerprint=baseline_result_fingerprint,
                baseline_had_result_shell=baseline_had_result_shell,
                observed_start=observed_start,
                max_progress=max_progress,
                elapsed=elapsed,
            )
            if ready:
                logging.info("平台回测完成，判定为本轮新结果：%s；特征：%s", reason, await result_feature_summary(page, text))
                return text
        if has_concrete_result and not new_result_seen and elapsed >= 30:
            if recent_progress_active:
                logging.warning("页面仍显示旧回测结果，但新近观察到运行进度，继续等待")
            elif elapsed >= 75:
                raise AutomationFlowError("[AUTOMATION] 点击 Run 后未触发新的可确认回测结果，页面仍显示旧结果；这是网页自动化或平台未接受运行请求的问题，不应交给 DeepSeek 修改代码")
            else:
                logging.warning("页面仍显示旧回测结果，尚未观察到新的运行进度或结果变化，继续等待")

        await asyncio.sleep(result_poll_interval_seconds(config))
    recovered_text = await final_recovery_result_text(
        page,
        config,
        baseline_fingerprint=baseline_result_fingerprint,
        baseline_had_result_shell=baseline_had_result_shell,
        observed_start=observed_start,
        max_progress=max_progress,
        started=started,
    )
    if recovered_text:
        return recovered_text
    raise AutomationFlowError("[AUTOMATION_TIMEOUT] 平台长时间未返回结果")


async def final_recovery_result_text(
    page: Page,
    config: WorkflowConfig,
    *,
    baseline_fingerprint: str,
    baseline_had_result_shell: bool,
    observed_start: bool,
    max_progress: float,
    started: float,
) -> str:
    logging.info("%s final recovery check before timeout", RESULT_UNCERTAIN)
    await asyncio.sleep(FINAL_RECOVERY_DELAY)
    try:
        await ensure_simulate_auth(page, config, "final_recovery_before_collect")
        await reveal_result_panels(page, include_show_test_period=True)
        text = await collect_result_text(page)
        await ensure_simulate_auth(page, config, "final_recovery_after_collect", current_body=text)
    except Exception as exc:
        logging.info("%s final recovery fetch failed: %s", RESULT_UNCERTAIN, exc)
        return ""
    if not text.strip() or not looks_like_concrete_backtest_result(text):
        logging.info("%s final recovery did not find concrete result", RESULT_UNCERTAIN)
        return ""

    ready, reason = result_ready_for_current_run(
        current_text=text,
        baseline_fingerprint=baseline_fingerprint,
        baseline_had_result_shell=baseline_had_result_shell,
        observed_start=observed_start,
        max_progress=max_progress,
        elapsed=time.time() - started,
    )
    if not ready:
        logging.info("%s final recovery rejected visible result: %s", RESULT_UNCERTAIN, reason)
        return ""

    detection = await detect_current_success_state(page, config, text)
    if detection.template_success:
        logging.info("Final recovery accepted confirmed success result: %s", detection.reason)
        return text
    if detection.candidate_success:
        latest_text, latest_detection = await stabilize_success_visibility(
            page,
            config,
            text,
            alpha_name="final_recovery",
            code="",
        )
        if latest_detection.template_success:
            logging.info("Final recovery accepted stabilized success candidate: %s", latest_detection.reason)
            return latest_text

    logging.info("Final recovery accepted concrete result for parser: %s", reason)
    return text


async def read_latest_success_for_final_recovery(
    supervisor: BrowserSupervisor,
    *,
    alpha_name: str,
    code: str,
    config: WorkflowConfig,
    template_file: str = "",
) -> SimulationResult | None:
    session = await supervisor.new_alpha_session(f"{alpha_name}_final_recovery")
    page = session.page
    try:
        await ensure_authenticated(page, config, target_url=SIMULATE_URL)
        await wait_visible_any(page, selector_config(config, "simulate_ready", ["body"]), timeout=30000)
        await ensure_simulate_auth(page, config, "max_loop_final_recovery", rerun_on_reauth=False)
        await ensure_code_editor_visible(page)
        await reveal_result_panels(page, include_show_test_period=True)
        text = await collect_result_text(page)
        if not result_matches_current_alpha(text, alpha_name, code):
            logging.info("%s max_loop recovery rejected result that does not match current alpha", RESULT_UNCERTAIN)
            return None
        text, detection = await stabilize_success_visibility(
            page,
            config,
            text,
            alpha_name=alpha_name,
            code=code,
            template_file=template_file,
        )
        if not detection.template_success:
            return None
        quality = parse_quality_report(text)
        metrics = extract_metrics(text)
        platform_sc = await collect_platform_sc_safely(
            page,
            alpha_name=alpha_name,
            timeout_seconds=max(1, int(getattr(config, "platform_sc_timeout_seconds", 90) or 90)),
        ) if bool(getattr(config, "enable_platform_sc_check", True)) else {"status": "skipped", "source": "platform", "reason": "disabled_by_config"}
        metrics = apply_platform_sc_to_metrics(metrics, platform_sc)
        screenshot_path = await capture_screenshot(page, alpha_name, "final_recovery")
        emit_template_success_event(alpha_id=alpha_name, detection=detection, template_file=template_file)
        return SimulationResult(
            ok=True,
            code=code,
            alpha_name=alpha_name,
            metrics=metrics,
            quality=quality,
            page_text=text,
            screenshot=screenshot_path,
            template_success=True,
            template_success_reason=detection.reason,
            success_candidate=detection.candidate_success,
            result_uncertain=False,
            platform_sc=platform_sc,
        )
    except Exception as exc:
        logging.info("%s max_loop final recovery failed: %s", RESULT_UNCERTAIN, exc)
        return None
    finally:
        await supervisor.close_session(session, persist_storage=False)


def result_matches_current_alpha(text: str, alpha_name: str, code: str) -> bool:
    if alpha_name and re.search(rf"\b{re.escape(alpha_name)}\b", text or ""):
        return True
    compact_code = re.sub(r"\s+", "", code or "").lower()
    if len(compact_code) < 24:
        return False
    compact_text = re.sub(r"\s+", "", text or "").lower()
    return compact_code in compact_text or compact_code[: min(120, len(compact_code))] in compact_text


async def result_shell_visible(page: Page) -> bool:
    try:
        return bool(
            await page.evaluate(
                """() => {
                    const normalize = text => String(text || '').replace(/\\s+/g, ' ').trim();
                    const visible = el => {
                        const style = window.getComputedStyle(el);
                        const rect = el.getBoundingClientRect();
                        return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
                    };
                    const blockedByOverlay = el => {
                        const rect = el.getBoundingClientRect();
                        const x = Math.max(1, Math.min(window.innerWidth - 1, rect.left + Math.min(rect.width / 2, 40)));
                        const y = Math.max(1, Math.min(window.innerHeight - 1, rect.top + Math.min(rect.height / 2, 40)));
                        const top = document.elementFromPoint(x, y);
                        if (!top || top === el || el.contains(top) || top.contains(el)) return false;
                        const overlay = top.closest('[role="dialog"],[role="menu"],[class*="modal" i],[class*="popover" i],[class*="dropdown" i]');
                        return Boolean(overlay && !overlay.contains(el));
                    };
                    const settingsPanelLike = node => {
                        const attrs = [
                            node.tagName,
                            node.id || '',
                            String(node.className || ''),
                            node.getAttribute('role') || '',
                            node.getAttribute('aria-label') || '',
                            node.getAttribute('data-testid') || ''
                        ].join(' ');
                        const rect = node.getBoundingClientRect();
                        return /\\b(?:dialog|menu|popover|dropdown)\\b|alphas-details-sections__settings|settings-sortable|settings-content|settings-actions|settings-sortable-item/i.test(attrs) ||
                            (rect.width >= 120 && rect.width <= Math.min(window.innerWidth * 0.8, 900) &&
                             rect.height >= 80 && rect.height <= window.innerHeight * 0.95 &&
                             !(rect.width >= window.innerWidth * 0.85 || rect.height >= window.innerHeight * 0.98));
                    };
                    const inSettingsMenu = el => {
                        let node = el;
                        for (let depth = 0; node && depth < 10; depth += 1, node = node.parentElement) {
                            if (!settingsPanelLike(node)) continue;
                            const text = normalize(node.innerText || node.textContent || '');
                            const attrs = [
                                node.tagName,
                                node.id || '',
                                String(node.className || ''),
                                node.getAttribute('role') || '',
                                node.getAttribute('aria-label') || '',
                                node.getAttribute('data-testid') || ''
                            ].join(' ');
                            if (/\\bCustomize Alpha Details Menu\\b/i.test(text)) return true;
                            if (/Drag the containers to rearrange/i.test(text) && /\\bReset\\b/i.test(text) && /\\bApply\\b/i.test(text)) return true;
                            if (/alphas-details-sections__settings|settings-sortable|settings-content|settings-actions|settings-sortable-item/i.test(attrs) && /\\bCustomize Alpha Details Menu\\b/i.test(text)) return true;
                        }
                        return false;
                    };
                    const resultRe = /IS Summary|Aggregate Data|Last Run|\\b\\d+\\s+(PASS|FAIL|PENDING)\\b|\\b(?:Sharpe|Fitness|Turnover|Drawdown|Margin|Returns)\\b[\\s\\S]{0,80}\\b-?\\d+(?:\\.\\d+)?%?/i;
                    const detailRe = /result|summary|testing|alpha-detail|alpha detail|details|performance|backtest|simulation/i;
                    const noiseRe = /TIP|Try submitting Alphas|Properties|Tutorial Checks|Tutorial task|Exit tutorial mode|Customize Alpha Details Menu/i;
                    for (const el of Array.from(document.querySelectorAll('body *')).slice(0, 8000)) {
                        if (!visible(el)) continue;
                        if (blockedByOverlay(el)) continue;
                        if (inSettingsMenu(el)) continue;
                        const text = normalize(el.innerText || el.textContent || '');
                        if (!text || text.length < 4 || text.length > 1800) continue;
                        if (!resultRe.test(text)) continue;
                        const attrs = [
                            el.tagName,
                            el.id || '',
                            String(el.className || ''),
                            el.getAttribute('role') || '',
                            el.getAttribute('aria-label') || '',
                            el.getAttribute('data-testid') || ''
                        ].join(' ');
                        if (/nav|navigation|sidebar|menu|topbar|navbar|header/i.test(attrs) && text.length < 260) continue;
                        if (noiseRe.test(text) && !/IS Summary|Last Run|\\b\\d+\\s+(PASS|FAIL|PENDING)\\b/i.test(text)) continue;
                        if (!detailRe.test(attrs + ' ' + text) && !/IS Summary|Last Run|\\b\\d+\\s+(PASS|FAIL|PENDING)\\b/i.test(text)) continue;
                        return true;
                    }
                    return false;
                }"""
            )
        )
    except Exception:
        return False


async def result_feature_summary(page: Page, text: str) -> str:
    features: list[str] = []
    for label in ["IS Summary", "IS Testing Status", "PASS", "FAIL", "PENDING", "Sharpe", "Fitness", "Turnover"]:
        if re.search(rf"\b{re.escape(label)}\b", text, re.I):
            features.append(label)
    try:
        url = page.url
        if url:
            features.append(url)
    except Exception:
        pass
    return ", ".join(features[:12]) or "result region"


async def read_result_or_body_text(page: Page) -> str:
    focused = await collect_focused_result_text(page)
    if focused.strip():
        return focused
    return await safe_body_text(page)


async def result_text_strict(page: Page) -> str:
    return await collect_focused_result_text(page)


async def show_test_period_button_visible(page: Page) -> bool:
    try:
        result = await page.evaluate(
            """() => {
                const normalize = text => String(text || '').replace(/\\s+/g, ' ').trim();
                const visible = el => {
                    if (!el) return false;
                    const style = window.getComputedStyle(el);
                    const rect = el.getBoundingClientRect();
                    return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
                };
                const inResultRegion = el => {
                    let node = el;
                    for (let depth = 0; node && depth < 10; depth += 1, node = node.parentElement) {
                        const text = normalize(node.innerText || node.textContent || '');
                        const attrs = [
                            node.tagName,
                            node.id || '',
                            String(node.className || ''),
                            node.getAttribute('role') || '',
                            node.getAttribute('aria-label') || '',
                            node.getAttribute('data-testid') || ''
                        ].join(' ');
                        if (/\\bCustomize Alpha Details Menu\\b/i.test(text)) return false;
                        if (/Drag the containers to rearrange/i.test(text) && /\\bReset\\b/i.test(text) && /\\bApply\\b/i.test(text)) return false;
                        if (/alphas-details-sections__settings|settings-sortable|settings-content|settings-actions|settings-sortable-item/i.test(attrs) && /\\bCustomize Alpha Details Menu\\b/i.test(text)) return false;
                        if (/IS Summary|IS Testing Status|Performance Comparison|Aggregate Data|Last Run|\\b\\d+\\s+(PASS|FAIL|PENDING)\\b/i.test(text)) return true;
                        if (/result|summary|testing|alpha-detail|details|performance|backtest/i.test(attrs)) return true;
                    }
                    return false;
                };
                for (const raw of Array.from(document.querySelectorAll('button,[role="button"]')).slice(0, 500)) {
                    if (!visible(raw)) continue;
                    if (raw.disabled || raw.getAttribute('aria-disabled') === 'true') continue;
                    const text = normalize(raw.innerText || raw.textContent || raw.getAttribute('aria-label') || raw.getAttribute('title') || '');
                    if (/^show test period$/i.test(text) && inResultRegion(raw)) return true;
                }
                return false;
            }"""
        )
        return bool(result)
    except Exception:
        return False


async def detect_and_click_show_test_period(page: Page) -> bool:
    """Click Show test period only when the button exists, is visible, and belongs to results."""
    if not await try_close_alpha_details_settings_menu(page, "before_show_test_period_click"):
        return False
    try:
        clicked = await page.evaluate(
            """() => {
                const normalize = text => String(text || '').replace(/\\s+/g, ' ').trim();
                const visible = el => {
                    if (!el) return false;
                    const style = window.getComputedStyle(el);
                    const rect = el.getBoundingClientRect();
                    return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
                };
                const inResultRegion = el => {
                    let node = el;
                    for (let depth = 0; node && depth < 10; depth += 1, node = node.parentElement) {
                        const text = normalize(node.innerText || node.textContent || '');
                        const attrs = [
                            node.tagName,
                            node.id || '',
                            String(node.className || ''),
                            node.getAttribute('role') || '',
                            node.getAttribute('aria-label') || '',
                            node.getAttribute('data-testid') || ''
                        ].join(' ');
                        if (/\\bCustomize Alpha Details Menu\\b/i.test(text)) return false;
                        if (/Drag the containers to rearrange/i.test(text) && /\\bReset\\b/i.test(text) && /\\bApply\\b/i.test(text)) return false;
                        if (/alphas-details-sections__settings|settings-sortable|settings-content|settings-actions|settings-sortable-item/i.test(attrs) && /\\bCustomize Alpha Details Menu\\b/i.test(text)) return false;
                        if (/IS Summary|IS Testing Status|Performance Comparison|PASS|FAIL|PENDING|Sharpe|Fitness|Turnover|Drawdown|Margin|Returns|test period/i.test(text)) return true;
                        if (/result|summary|testing|status|alpha-detail|details|panel|period/i.test(attrs)) return true;
                    }
                    return false;
                };
                for (const raw of Array.from(document.querySelectorAll('button,[role="button"]')).slice(0, 600)) {
                    if (!visible(raw)) continue;
                    const text = normalize(raw.innerText || raw.textContent || raw.getAttribute('aria-label') || raw.getAttribute('title') || '');
                    if (/^hide test period$/i.test(text) && inResultRegion(raw)) return 'expanded';
                }
                const candidates = [];
                for (const raw of Array.from(document.querySelectorAll('button,[role="button"]')).slice(0, 600)) {
                    if (!visible(raw)) continue;
                    if (raw.disabled || raw.getAttribute('aria-disabled') === 'true') continue;
                    const text = normalize(raw.innerText || raw.textContent || raw.getAttribute('aria-label') || raw.getAttribute('title') || '');
                    if (!/^show test period$/i.test(text)) continue;
                    if (!inResultRegion(raw)) continue;
                    const rect = raw.getBoundingClientRect();
                    candidates.push({el: raw, top: rect.top, left: rect.left});
                }
                candidates.sort((a, b) => a.top - b.top || a.left - b.left);
                const best = candidates[0];
                if (!best) return false;
                best.el.scrollIntoView({block: 'center', inline: 'center'});
                best.el.dispatchEvent(new MouseEvent('mousedown', {bubbles: true, cancelable: true}));
                best.el.dispatchEvent(new MouseEvent('mouseup', {bubbles: true, cancelable: true}));
                best.el.click();
                return true;
            }"""
        )
        if clicked == "expanded":
            await mark_show_test_period_revealed(page)
            return True
        if clicked:
            logging.info("检测到并展开 Show test period")
            await mark_show_test_period_revealed(page)
            await asyncio.sleep(0.8)
        return bool(clicked)
    except Exception:
        return False


async def mark_show_test_period_revealed(page: Page) -> None:
    try:
        focused = await collect_focused_result_text(page)
        text = focused or await safe_body_text(page, timeout=3000)
        fingerprint = result_fingerprint(text)
        await page.evaluate(
            """fingerprint => {
                window.__wq_show_test_period_revealed = {
                    fingerprint: String(fingerprint || ''),
                    at: Date.now()
                };
            }""",
            fingerprint,
        )
    except Exception:
        pass


async def show_test_period_revealed_on_page(page: Page) -> bool:
    try:
        focused = await collect_focused_result_text(page)
        text = focused or await safe_body_text(page, timeout=3000)
        current_fingerprint = result_fingerprint(text)
        return bool(
            await page.evaluate(
                """currentFingerprint => {
                    const normalize = text => String(text || '').replace(/\\s+/g, ' ').trim();
                    const visible = el => {
                        if (!el) return false;
                        const style = window.getComputedStyle(el);
                        const rect = el.getBoundingClientRect();
                        return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
                    };
                    const inResultRegion = el => {
                        let node = el;
                        for (let depth = 0; node && depth < 10; depth += 1, node = node.parentElement) {
                            const text = normalize(node.innerText || node.textContent || '');
                            const attrs = [
                                node.tagName,
                                node.id || '',
                                String(node.className || ''),
                                node.getAttribute('role') || '',
                                node.getAttribute('aria-label') || '',
                                node.getAttribute('data-testid') || ''
                            ].join(' ');
                            if (/\\bCustomize Alpha Details Menu\\b/i.test(text)) return false;
                            if (/Drag the containers to rearrange/i.test(text) && /\\bReset\\b/i.test(text) && /\\bApply\\b/i.test(text)) return false;
                            if (/IS Summary|IS Testing Status|Performance Comparison|PASS|FAIL|PENDING|Sharpe|Fitness|Turnover|Drawdown|Margin|Returns|test period/i.test(text)) return true;
                            if (/result|summary|testing|status|alpha-detail|details|panel|period/i.test(attrs)) return true;
                        }
                        return false;
                    };
                    for (const raw of Array.from(document.querySelectorAll('button,[role="button"]')).slice(0, 600)) {
                        if (!visible(raw)) continue;
                        const text = normalize(raw.innerText || raw.textContent || raw.getAttribute('aria-label') || raw.getAttribute('title') || '');
                        if (/^hide test period$/i.test(text) && inResultRegion(raw)) return true;
                    }
                    const marker = window.__wq_show_test_period_revealed;
                    if (marker && typeof marker === 'object') {
                        const age = Date.now() - Number(marker.at || 0);
                        if (age >= 0 && age <= 3600000 && marker.fingerprint && marker.fingerprint === currentFingerprint) return true;
                    }
                    return false;
                }""",
                current_fingerprint,
            )
        )
    except Exception:
        return False


def has_new_result(text: str, baseline_fingerprint: str) -> bool:
    current = result_fingerprint(text)
    return bool(current and current != baseline_fingerprint)


def wait_result_max_seconds(config: WorkflowConfig) -> int:
    configured = getattr(config, "wait_result_max_seconds", WAIT_RESULT_DEFAULT_MAX_SECONDS)
    try:
        value = int(configured)
    except (TypeError, ValueError):
        value = WAIT_RESULT_DEFAULT_MAX_SECONDS
    return max(WAIT_RESULT_MIN_SECONDS, min(WAIT_RESULT_DEFAULT_MAX_SECONDS, value))


def wait_result_start_timeout_seconds(config: WorkflowConfig) -> int:
    try:
        return max(1, int(getattr(config, "wait_result_start_timeout_seconds", WAIT_RESULT_START_TIMEOUT_SECONDS)))
    except (TypeError, ValueError):
        return WAIT_RESULT_START_TIMEOUT_SECONDS


def result_stable_reads(config: WorkflowConfig) -> int:
    try:
        return max(1, int(getattr(config, "result_stable_reads", RESULT_STABLE_READS)))
    except (TypeError, ValueError):
        return RESULT_STABLE_READS


def result_poll_interval_seconds(config: WorkflowConfig) -> float:
    try:
        return max(0.5, float(getattr(config, "result_poll_interval_seconds", RESULT_POLL_INTERVAL_SECONDS)))
    except (TypeError, ValueError):
        return RESULT_POLL_INTERVAL_SECONDS


def result_dom_stable_window_seconds(config: WorkflowConfig) -> float:
    try:
        return max(0.0, float(getattr(config, "result_dom_stable_window_seconds", RESULT_DOM_STABLE_WINDOW_SECONDS)))
    except (TypeError, ValueError):
        return RESULT_DOM_STABLE_WINDOW_SECONDS


def result_ready_for_current_run(
    *,
    current_text: str,
    baseline_fingerprint: str,
    baseline_had_result_shell: bool,
    observed_start: bool,
    max_progress: float,
    elapsed: float,
) -> tuple[bool, str]:
    current_fingerprint = result_fingerprint(current_text)
    if not looks_like_concrete_backtest_result(current_text):
        return False, "结果区域尚无具体指标"
    if baseline_fingerprint:
        if current_fingerprint and current_fingerprint != baseline_fingerprint:
            return True, "结果指纹已不同于 Run 前旧结果"
        return False, "结果指纹仍等于 Run 前旧结果"
    if baseline_had_result_shell:
        if current_fingerprint and observed_start and max_progress >= 15 and elapsed >= 20:
            return True, "fresh result accepted after observed run progress with fingerprintless baseline shell"
        return False, "baseline had result shell but no stable fingerprint"
    if not observed_start:
        return False, "run start not observed"
    if max_progress < 15:
        return False, "progress has not crossed 15%"
    if elapsed < 20:
        return False, "waiting for result to stabilize"
    return True, "fresh result accepted after observed run progress"


def result_fingerprint(text: str) -> str:
    if not text:
        return ""
    text = strip_submit_criteria_tutorial_noise(text)
    if not text:
        return ""
    parts: list[str] = []
    for pattern in [r"Last saved\s+[^\n]+", r"Last Run:\s*[^\n]+"]:
        match = re.search(pattern, text, re.I)
        if match:
            parts.append(match.group(0))
    for label in ["PASS", "FAIL", "PENDING"]:
        matches = re.findall(rf"\b(\d+)\s+{label}\b", text, re.I)
        if matches:
            parts.append(f"{label}:{matches[-1]}")
    metrics = extract_metrics(text)
    for key in sorted(metrics):
        parts.append(f"{key}:{metrics[key]:.6g}")
    if not parts:
        return ""
    return re.sub(r"\s+", " ", "\n".join(parts)).strip().lower()


def stable_result_fingerprint(text: str) -> str:
    if not text:
        return ""
    try:
        text = strip_submit_criteria_tutorial_noise(text)
        if not text:
            return ""
        parts: list[str] = []
        metrics = extract_metrics(text)
        for key in ["sharpe", "fitness", "turnover", "margin"]:
            if key in metrics:
                parts.append(f"{key}:{metrics[key]:.6g}")
        for label in ["PASS", "FAIL", "PENDING"]:
            matches = re.findall(rf"\b(\d+)\s+{label}\b", text, re.I)
            if matches:
                parts.append(f"{label.lower()}:{matches[-1]}")
        for label, patterns in {
            "long_count": [
                r"\bLong\s+Count\b[^\d]*(\d+)",
                r"\bLongs?\b[^\d]*(\d+)",
            ],
            "short_count": [
                r"\bShort\s+Count\b[^\d]*(\d+)",
                r"\bShorts?\b[^\d]*(\d+)",
            ],
        }.items():
            for pattern in patterns:
                match = re.search(pattern, text, re.I)
                if match:
                    parts.append(f"{label}:{match.group(1)}")
                    break
        if re.search(r"\bIS Summary\b", text, re.I):
            parts.append("is_summary:1")
        if not parts:
            return ""
        canonical = "|".join(parts)
        digest = hashlib.sha1(canonical.encode("utf-8", errors="ignore")).hexdigest()[:16]
        return f"{digest}:{canonical}"
    except Exception:
        return ""


def looks_like_result_shell_text(text: str) -> bool:
    if not text:
        return False
    compact = re.sub(r"\s+", " ", text).strip()
    if not compact:
        return False
    if looks_like_alpha_details_settings_text(compact) and not re.search(
        r"IS Summary|Last Run|\b\d+\s+(?:PASS|FAIL|PENDING)\b|\b(?:Sharpe|Fitness|Turnover|Drawdown|Margin|Returns)\b[\s\S]{0,80}\b-?\d+(?:\.\d+)?%?",
        compact,
        re.I,
    ):
        return False
    if re.search(r"TIP|Try submitting Alphas|Try creating a submittable Alpha|About Alpha Submit Criteria|Tutorial Checks|Tutorial task|Exit tutorial mode", compact, re.I):
        if not re.search(r"IS Summary|Last Run|\b\d+\s+(?:PASS|FAIL|PENDING)\b", compact, re.I):
            return False
    return bool(
        re.search(
            r"IS Summary|Aggregate Data|Last Run|\b\d+\s+(?:PASS|FAIL|PENDING)\b|\b(?:Sharpe|Fitness|Turnover|Drawdown|Margin|Returns)\b[\s\S]{0,80}\b-?\d+(?:\.\d+)?%?",
            compact,
            re.I,
        )
    )


def looks_like_submit_criteria_tutorial_noise(text: str) -> bool:
    compact = re.sub(r"\s+", " ", text or "").strip()
    if not compact:
        return False
    return bool(
        re.search(r"\bAbout Alpha Submit Criteria\b|\bTry creating a submittable Alpha\b|\bSubmit Criteria\b", compact, re.I)
        and re.search(r"\b(?:Sharpe|Fitness|Turnover|Returns|Drawdown|Margin)\b", compact, re.I)
    )


def strip_submit_criteria_tutorial_noise(text: str) -> str:
    if not text or not looks_like_submit_criteria_tutorial_noise(text):
        return text or ""
    match = re.search(r"\bIS Summary\b|\bAggregate Data\b|\bLast Run\b|\b\d+\s+(?:PASS|FAIL|PENDING)\b", text, re.I)
    if match:
        return text[match.start() :]
    return ""


def looks_like_alpha_details_settings_text(text: str) -> bool:
    compact = re.sub(r"\s+", " ", text or "").strip()
    if not compact:
        return False
    return bool(
        re.search(r"\bCustomize Alpha Details Menu\b", compact, re.I)
        or (
            re.search(r"Drag the containers to rearrange", compact, re.I)
            and re.search(r"\bReset\b", compact, re.I)
            and re.search(r"\bApply\b", compact, re.I)
        )
    )


async def reveal_result_panels(page: Page, *, include_show_test_period: bool = True) -> None:
    if not await try_close_alpha_details_settings_menu(page, "before_reveal_result_panels"):
        return
    selectors = [
        'button:has-text("Summary")',
        '[role="tab"]:has-text("Summary")',
        '[role="button"]:has-text("Summary")',
        'button:has-text("Testing Status")',
        '[role="tab"]:has-text("Testing Status")',
        '[role="button"]:has-text("Testing Status")',
        'button:has-text("Performance Comparison")',
        '[role="tab"]:has-text("Performance Comparison")',
    ]
    if include_show_test_period:
        await detect_and_click_show_test_period(page)
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            if await locator.is_visible(timeout=400):
                text = await locator.inner_text(timeout=500)
                if not await is_result_region_control(locator):
                    continue
                if re.search(r"\bSubmit\b|提交", text, re.I):
                    continue
                await locator.click(timeout=1000, force=True)
                await asyncio.sleep(0.5)
        except Exception:
            continue


async def collect_result_text(page: Page) -> str:
    if not await show_test_period_revealed_on_page(page):
        await detect_and_click_show_test_period(page)
    await reveal_result_panels(page, include_show_test_period=False)
    base_text = await collect_focused_result_text(page)
    expanded_sections = await collect_expanded_testing_status(page)
    if expanded_sections:
        logging.info(
            "Expanded and collected IS Testing Status details: %s",
            ", ".join(section["label"] for section in expanded_sections),
        )
        blocks = ["", "EXPANDED IS TESTING STATUS"]
        for section in expanded_sections:
            blocks.append(f"[{section['label']}]\n{section['text']}")
        return base_text + "\n" + "\n\n".join(blocks)
    return base_text


async def collect_focused_result_text(page: Page) -> str:
    """Collect visible result content while ignoring tutorial and navigation noise."""
    try:
        raw = await page.evaluate(
            """() => {
                const normalize = text => String(text || '').replace(/\\s+/g, ' ').trim();
                const visible = el => {
                    const style = window.getComputedStyle(el);
                    const rect = el.getBoundingClientRect();
                    return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
                };
                const blockedByOverlay = el => {
                    const rect = el.getBoundingClientRect();
                    const points = [
                        [rect.left + rect.width / 2, rect.top + rect.height / 2],
                        [rect.left + Math.min(rect.width - 1, 12), rect.top + Math.min(rect.height - 1, 12)]
                    ];
                    for (const [rawX, rawY] of points) {
                        const x = Math.max(1, Math.min(window.innerWidth - 1, rawX));
                        const y = Math.max(1, Math.min(window.innerHeight - 1, rawY));
                        const top = document.elementFromPoint(x, y);
                        if (!top || top === el || el.contains(top) || top.contains(el)) continue;
                        const overlay = top.closest('[role="dialog"],[role="menu"],[class*="modal" i],[class*="popover" i],[class*="dropdown" i]');
                        if (overlay && !overlay.contains(el)) return true;
                    }
                    return false;
                };
                    const settingsPanelLike = node => {
                        const attrs = [
                            node.tagName,
                            node.id || '',
                            String(node.className || ''),
                            node.getAttribute('role') || '',
                            node.getAttribute('aria-label') || '',
                            node.getAttribute('data-testid') || ''
                        ].join(' ');
                        const rect = node.getBoundingClientRect();
                        return /\\b(?:dialog|menu|popover|dropdown)\\b|alphas-details-sections__settings|settings-sortable|settings-content|settings-actions|settings-sortable-item/i.test(attrs) ||
                            (rect.width >= 120 && rect.width <= Math.min(window.innerWidth * 0.8, 900) &&
                             rect.height >= 80 && rect.height <= window.innerHeight * 0.95 &&
                             !(rect.width >= window.innerWidth * 0.85 || rect.height >= window.innerHeight * 0.98));
                    };
                    const inSettingsMenu = el => {
                        let node = el;
                        for (let depth = 0; node && depth < 10; depth += 1, node = node.parentElement) {
                            if (!settingsPanelLike(node)) continue;
                            const text = normalize(node.innerText || node.textContent || '');
                            const attrs = [
                                node.tagName,
                            node.id || '',
                            String(node.className || ''),
                            node.getAttribute('role') || '',
                            node.getAttribute('aria-label') || '',
                            node.getAttribute('data-testid') || ''
                        ].join(' ');
                        if (/\\bCustomize Alpha Details Menu\\b/i.test(text)) return true;
                        if (/Drag the containers to rearrange/i.test(text) && /\\bReset\\b/i.test(text) && /\\bApply\\b/i.test(text)) return true;
                        if (/alphas-details-sections__settings|settings-sortable|settings-content|settings-actions|settings-sortable-item/i.test(attrs) && /\\bCustomize Alpha Details Menu\\b/i.test(text)) return true;
                    }
                    return false;
                };
                const isNoise = text => /Exit tutorial mode|Tutorial Checks|Tutorial task|Completed task|Customize Alpha Details Menu/i.test(text);
                const resultRe = /IS Summary|Aggregate Data|Last Run|\\b\\d+\\s+(PASS|FAIL|PENDING)\\b|\\b(?:Sharpe|Fitness|Turnover|Drawdown|Margin|Returns)\\b[\\s\\S]{0,80}\\b-?\\d+(?:\\.\\d+)?%?/i;
                const detailRe = /result|summary|testing|alpha-detail|details|performance|backtest|simulation/i;
                const blocks = [];
                for (const el of Array.from(document.querySelectorAll('body *')).slice(0, 10000)) {
                    if (!visible(el)) continue;
                    if (blockedByOverlay(el)) continue;
                    if (inSettingsMenu(el)) continue;
                    const text = normalize(el.innerText || el.textContent || '');
                    if (!text || text.length < 4 || text.length > 3000) continue;
                    if (!resultRe.test(text)) continue;
                    const attrs = [
                        el.tagName,
                        el.id || '',
                        String(el.className || ''),
                        el.getAttribute('role') || '',
                        el.getAttribute('aria-label') || '',
                        el.getAttribute('data-testid') || ''
                    ].join(' ');
                    if (/nav|navigation|sidebar|menu|topbar|navbar|header/i.test(attrs) && text.length < 400) continue;
                    if (!detailRe.test(attrs + ' ' + text) && !/IS Summary|Last Run|\\b\\d+\\s+(PASS|FAIL|PENDING)\\b/i.test(text)) continue;
                    const cleaned = text.split(/Exit tutorial mode|Tutorial Checks|Tutorial task not met|Completed task/i)[0].trim();
                    blocks.push(cleaned && !isNoise(cleaned) ? cleaned : text);
                }
                blocks.sort((a, b) => b.length - a.length);
                return blocks.slice(0, 12);
            }"""
        )
    except Exception:
        raw = []

    pieces: list[str] = []
    for item in raw or []:
        text = strip_tutorial_noise(normalize_message(str(item)))
        if not text or looks_like_navigation_noise(text) or looks_like_alpha_details_settings_text(text):
            continue
        pieces.append(text)
    focused = "\n".join(dedupe_plain_messages(pieces))
    if focused.strip():
        return focused[:20000]
    return ""


async def collect_expanded_testing_status(page: Page) -> list[dict[str, str]]:
    await click_result_tab(page, "Testing Status")
    sections: list[dict[str, str]] = []
    for label in ["FAIL", "PENDING", "PASS"]:
        clicked = await click_status_bucket(page, label)
        if not clicked:
            continue
        await asyncio.sleep(0.8)
        text = await extract_testing_status_detail_text(page, label)
        if text:
            sections.append({"label": label, "text": text})
    return sections


async def click_result_tab(page: Page, label: str) -> bool:
    selectors = [
        f'button:has-text("{label}")',
        f'[role="tab"]:has-text("{label}")',
        f'[role="button"]:has-text("{label}")',
    ]
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            if not await locator.is_visible(timeout=500):
                continue
            text = await locator.inner_text(timeout=500)
            if not await is_result_region_control(locator):
                continue
            if re.search(r"\bSubmit\b|提交", text, re.I):
                continue
            await locator.click(timeout=1200, force=True)
            return True
        except Exception:
            continue
    return False


async def click_status_bucket(page: Page, label: str) -> bool:
    selectors = [
        f'text=/\\b\\d+\\s+{label}\\b/i',
        f'button:has-text("{label}")',
        f'[role="button"]:has-text("{label}")',
        f'[role="tab"]:has-text("{label}")',
        f'[class*="status" i]:has-text("{label}")',
    ]
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            if not await locator.is_visible(timeout=600):
                continue
            if not await is_result_region_control(locator):
                continue
            await locator.click(timeout=1500, force=True)
            logging.info("Expanded IS Testing Status: %s selector=%s", label, selector)
            return True
        except Exception:
            continue
    return False


async def is_result_region_control(locator) -> bool:
    try:
        return bool(
            await locator.evaluate(
                """el => {
                    const normalize = text => String(text || '').replace(/\\s+/g, ' ').trim();
                    let node = el;
                    for (let depth = 0; node && depth < 8; depth += 1, node = node.parentElement) {
                        const text = normalize(node.innerText || node.textContent || '');
                        const attrs = [
                            node.tagName,
                            node.id || '',
                            String(node.className || ''),
                            node.getAttribute('role') || '',
                            node.getAttribute('aria-label') || '',
                            node.getAttribute('data-testid') || ''
                        ].join(' ');
                        if (/\\bCustomize Alpha Details Menu\\b/i.test(text) || (/Drag the containers to rearrange/i.test(text) && /\\bReset\\b/i.test(text) && /\\bApply\\b/i.test(text))) {
                            return false;
                        }
                        if (/alphas-details-sections__settings|settings-sortable|settings-content|settings-actions|settings-sortable-item/i.test(attrs) && /\\bCustomize Alpha Details Menu\\b/i.test(text)) {
                            return false;
                        }
                        if (/IS Summary|IS Testing Status|Performance Comparison|Testing Status|Correlation|Properties|PASS|FAIL|PENDING/i.test(text)) {
                            return true;
                        }
                        if (/result|summary|testing|status|alpha-detail|details|tab|panel/i.test(attrs)) {
                            return true;
                        }
                    }
                    return false;
                }"""
            )
        )
    except Exception:
        return False


async def extract_testing_status_detail_text(page: Page, label: str) -> str:
    try:
        raw = await page.evaluate(
            """(label) => {
                const normalize = (text) => String(text || '').replace(/\\s+/g, ' ').trim();
                const visible = (el) => {
                    const style = window.getComputedStyle(el);
                    const rect = el.getBoundingClientRect();
                    return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
                };
                const wanted = new RegExp('\\\\b' + label + '\\\\b', 'i');
                const candidates = [];
                for (const el of Array.from(document.querySelectorAll('body *')).slice(0, 8000)) {
                    if (!visible(el)) continue;
                    const text = normalize(el.innerText || el.textContent || '');
                    if (!text || text.length < 8 || text.length > 2400) continue;
                    const attrs = [
                        el.tagName,
                        el.id || '',
                        String(el.className || ''),
                        el.getAttribute('role') || '',
                        el.getAttribute('aria-label') || '',
                        el.getAttribute('data-testid') || ''
                    ].join(' ');
                    if (/\\bCustomize Alpha Details Menu\\b/i.test(text) || (/Drag the containers to rearrange/i.test(text) && /\\bReset\\b/i.test(text) && /\\bApply\\b/i.test(text))) continue;
                    if (/alphas-details-sections__settings|settings-sortable|settings-content|settings-actions|settings-sortable-item/i.test(attrs) && /\\bCustomize Alpha Details Menu\\b/i.test(text)) continue;
                    const statusish = /status|test|check|result|accordion|collapse|panel|popover|tooltip|modal|drawer/i.test(attrs);
                    const hasAdvice = /cutoff|Self[- ]?correlation|Sub[- ]?universe|Turnover|Fitness|Sharpe|Margin|Drawdown|bucket\\(\\)|neutralize|pending|above|below|PASS|FAIL|PENDING/i.test(text);
                    if ((statusish || hasAdvice) && (wanted.test(text) || hasAdvice)) {
                        candidates.push(text);
                    }
                }
                candidates.sort((a, b) => a.length - b.length);
                return candidates.slice(0, 8);
            }""",
            label,
        )
    except Exception:
        return ""
    pieces: list[str] = []
    for item in raw or []:
        text = normalize_message(str(item))
        if not text or looks_like_navigation_noise(text):
            continue
        if len(text) > 1800:
            continue
        pieces.append(text)
    return "\n".join(dedupe_plain_messages(pieces))[:5000]


def looks_like_concrete_backtest_result(text: str) -> bool:
    if not text:
        return False
    concrete_patterns = [
        r"\b\d+\s+(?:PASS|FAIL|PENDING)\b",
        r"\bSharpe\b[\s\S]{0,80}\b-?\d+(?:\.\d+)?\b",
        r"\bFitness\b[\s\S]{0,80}\b-?\d+(?:\.\d+)?\b",
        r"\bTurnover\b[\s\S]{0,80}\b-?\d+(?:\.\d+)?%?\b",
        r"\bMargin\b[\s\S]{0,80}\b-?\d+(?:\.\d+)?%?\b",
        r"\bSub[- ]universe\s+Sharpe\b[\s\S]{0,120}\b-?\d+(?:\.\d+)?\b",
        r"\bSelf-correlation check\b[\s\S]{0,120}\b(?:PASS|FAIL|PENDING|above|below)\b",
    ]
    return any(re.search(pattern, text, re.I) for pattern in concrete_patterns)


async def visible_loading_indicator(page: Page) -> bool:
    try:
        return bool(
            await page.evaluate(
                """() => {
                    const traitRe = /(spinner|loading|loader|progress|skeleton|busy)/i;
                    for (const el of Array.from(document.querySelectorAll('body *')).slice(0, 6000)) {
                        const style = window.getComputedStyle(el);
                        const rect = el.getBoundingClientRect();
                        if (style.display === 'none' || style.visibility === 'hidden' || rect.width === 0 || rect.height === 0) continue;
                        const attrs = [
                            el.tagName,
                            el.id || '',
                            String(el.className || ''),
                            el.getAttribute('role') || '',
                            el.getAttribute('aria-busy') || '',
                            el.getAttribute('aria-label') || ''
                        ].join(' ');
                        const text = (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim();
                        const roleProgress = /role="?progressbar"?/i.test(attrs) || /\\bprogressbar\\b/i.test(attrs);
                        const loaderTrait = /(spinner|loading|loader|skeleton|busy)/i.test(attrs);
                        if (el.getAttribute('aria-busy') === 'true') return true;
                        if ((roleProgress || loaderTrait) && rect.width >= 10 && rect.height >= 10) return true;
                        if (/Saving\\.\\.\\.|Loading|Calculating/i.test(text)) return true;
                    }
                    return false;
                }"""
            )
        )
    except Exception:
        return False


async def simulate_run_loading_indicator(page: Page) -> bool:
    try:
        return bool(
            await page.evaluate(
                """() => {
                    const normalize = text => String(text || '').replace(/\\s+/g, ' ').trim();
                    const visible = el => {
                        const style = window.getComputedStyle(el);
                        const rect = el.getBoundingClientRect();
                        return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
                    };
                    const editor = document.querySelector('.monaco-editor, .cm-editor, .cm-content, textarea.inputarea');
                    const editorRect = editor ? editor.getBoundingClientRect() : null;
                    const nearEditor = el => {
                        if (!editorRect) return false;
                        const rect = el.getBoundingClientRect();
                        return rect.top >= editorRect.top - 180 && rect.top <= editorRect.bottom + 260 &&
                            rect.left >= editorRect.left - 120 && rect.left <= editorRect.right + 320;
                    };
                    const runTextRe = /running|simulating|queued|calculating|in progress|cancel the simulation|Simulations usually take|正在|运行中|排队|计算中/i;
                    for (const el of Array.from(document.querySelectorAll('body *')).slice(0, 8000)) {
                        if (!visible(el)) continue;
                        const text = normalize(el.innerText || el.textContent || '');
                        const attrs = [
                            el.tagName,
                            el.id || '',
                            String(el.className || ''),
                            el.getAttribute('role') || '',
                            el.getAttribute('aria-busy') || '',
                            el.getAttribute('aria-label') || '',
                            el.getAttribute('data-testid') || ''
                        ].join(' ');
                        if (runTextRe.test(text)) return true;
                        const progressish = /progressbar|spinner|loading|loader|busy/i.test(attrs);
                        if (!progressish) continue;
                        if (nearEditor(el) || /simulate|simulation|backtest|editor/i.test(attrs)) return true;
                    }
                    return false;
                }"""
            )
        )
    except Exception:
        return False


async def detect_platform_errors(page: Page, baseline_error_fingerprint: set[str] | None = None) -> str:
    messages: list[str] = []
    messages.extend(await collect_alert_like_messages(page))
    body_text = await safe_body_text(page, timeout=3000)
    messages.extend(extract_error_lines_from_text(body_text))
    filtered = dedupe_error_messages(messages)
    if baseline_error_fingerprint:
        filtered = [
            message
            for message in filtered
            if normalize_error_key(message) not in baseline_error_fingerprint
        ]
    return "\n".join(filtered)


def error_fingerprint(messages: list[str]) -> set[str]:
    return {normalize_error_key(message) for message in dedupe_error_messages(messages) if normalize_error_key(message)}


def normalize_error_key(message: str) -> str:
    return re.sub(r"\s+", " ", normalize_message(message).lower()).strip()


async def collect_alert_like_messages(page: Page) -> list[str]:
    """Find platform errors by shared DOM traits: toast, alert, negative message, red visible bar."""
    try:
        raw_items = await page.evaluate(
            """() => {
                const items = [];
                const traitRe = /(error|alert|danger|warning|warn|toast|notification|message|negative|invalid|failed|failure|validation)/i;
                const parseRgb = (value) => {
                    const m = String(value || '').match(/rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)/i);
                    return m ? [Number(m[1]), Number(m[2]), Number(m[3])] : null;
                };
                const isRedLike = (value) => {
                    const rgb = parseRgb(value);
                    if (!rgb) return false;
                    const [r, g, b] = rgb;
                    return r > 150 && g < 140 && b < 150;
                };
                for (const el of Array.from(document.querySelectorAll('body *')).slice(0, 6000)) {
                    const style = window.getComputedStyle(el);
                    const rect = el.getBoundingClientRect();
                    if (style.display === 'none' || style.visibility === 'hidden' || rect.width === 0 || rect.height === 0) continue;
                    const text = (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim();
                    if (!text || text.length < 6 || text.length > 1400) continue;
                    const attrs = [
                        el.tagName,
                        el.id || '',
                        String(el.className || ''),
                        el.getAttribute('role') || '',
                        el.getAttribute('aria-live') || '',
                        el.getAttribute('aria-label') || '',
                        el.getAttribute('data-testid') || ''
                    ].join(' ');
                    const roleAlert = /\\b(alert|status)\\b/i.test(attrs);
                    const trait = traitRe.test(attrs);
                    const redLike = isRedLike(style.backgroundColor) || isRedLike(style.color) || isRedLike(style.borderColor);
                    if (roleAlert || trait || redLike) items.push({ text, attrs });
                }
                return items;
            }"""
        )
    except Exception:
        return []

    messages: list[str] = []
    for item in raw_items:
        text = normalize_message(str(item.get("text", "")))
        if looks_like_platform_error(text):
            messages.append(text)
    return messages


def extract_error_lines_from_text(text: str) -> list[str]:
    normalized = normalize_message(text)
    messages: list[str] = []
    patterns = [
        r"Invalid number of inputs[^\n]*",
        r"should be exactly\s+\d+\s+input\(s\)[^\n]*",
        r"Incompatible unit[^\n]*",
        r"Exceeds limit[^\n]*",
        r"Syntax error[^\n]*",
        r"Unexpected (?:token|character)[^\n]*",
        r"Expression[^\n]*(?:invalid|failed)[^\n]*",
        r"Attempted to use[^\n]*(?:operator|field|data)[^\n]*",
        r"(?:inaccessible|unknown|unsupported)\s+(?:operator|field|data)[^\n]*",
        r"(?:Got|Not|No)[^\n]*(?:invalid|valid)[^\n]*(?:input|data|field)[^\n]*",
        r"(?:must|should)\s+be[^\n]*(?:input|data|vector|matrix|scalar|unit)[^\n]*",
        r"(?:Cannot|Can't|Unable to|Failed to)[^\n]*(?:simulate|compile|parse|run|save|load)[^\n]*",
        r"[^\n]*(?:Learn more|linkToCommonErrorMessages)[^\n]*",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, normalized, re.I):
            candidate = normalize_message(match.group(0))
            if looks_like_platform_error(candidate):
                messages.append(candidate)

    for line in normalized.splitlines():
        candidate = normalize_message(line)
        if looks_like_platform_error(candidate):
            messages.append(candidate)
    return messages


def looks_like_platform_error(text: str) -> bool:
    text = normalize_message(text)
    if not text or looks_like_quality_result(text) or looks_like_tutorial_status_noise(text) or looks_like_navigation_noise(text):
        return False
    if looks_like_quality_advice(text):
        return False
    if re.fullmatch(r"\s*trade_when\s+Operator\s*", text, re.I):
        return False
    if re.search(r"\btrade_when\s+Operator\b", text, re.I) and re.search(r"\bTry\s+using\s+exit\s+triggers\b", text, re.I):
        return False
    return bool(
        re.search(
            r"\b(?:Invalid|Incompatible|Exceeds|Syntax|Unexpected|unknown|inaccessible|unsupported|Attempted|Error|failed|failure|operator|token|character|expression)\b|错误|must\s+be|should\s+be|not\s+valid|invalid\s+input|\bunit(?:s)?\b|vector\s+data|matrix\s+data|scalar\s+data|Learn\s+more|linkToCommonErrorMessages",
            text,
            re.I,
        )
    )


def is_nonrecoverable_business_error(text: str) -> bool:
    return bool((text or "").startswith("[FINAL_CORRELATION]"))


def is_automation_result_error(text: str) -> bool:
    value = text or ""
    return "[AUTOMATION]" in value and not is_nonrecoverable_business_error(value)


def looks_like_tutorial_status_noise(text: str) -> bool:
    compact = re.sub(r"\s+", " ", text or "").strip()
    if not compact:
        return False
    return bool(
        re.search(r"(?:^|\b)Completed task\b", compact, re.I)
        or re.search(r"\bTry\s+(?:simulating|to\s+simulate)\b", compact, re.I)
        or re.search(r"\bTutorial\s+(?:task|mode|checks?)\b", compact, re.I)
        or re.search(r"\bExit tutorial mode\b", compact, re.I)
    )


def looks_like_quality_result(text: str) -> bool:
    if re.search(r"\b(IS Summary|IS Testing Status|Needs Improvement)\b", text, re.I):
        return True
    if re.search(r"\b(Tutorial Checks|Tutorial task not met|test period)\b", text, re.I):
        return True
    if re.search(r"\b\d+\s+(PASS|FAIL|PENDING)\b", text, re.I):
        return True
    if re.search(r"\b(?:Sharpe|Fitness|Turnover|Drawdown|Margin|Returns|Sub-universe Sharpe)\b.*\bcutoff\b", text, re.I):
        return True
    if re.search(r"\bSelf-correlation check pending\b", text, re.I):
        return True
    return False


def strip_tutorial_noise(text: str) -> str:
    if not text:
        return ""
    lines: list[str] = []
    for line in text.splitlines():
        compact = re.sub(r"\s+", " ", line).strip()
        if not compact:
            continue
        if re.search(r"Exit tutorial mode|Tutorial Checks|Tutorial task not met|Completed task|Show test period", compact, re.I):
            continue
        lines.append(line)
    return "\n".join(lines)


def looks_like_navigation_noise(text: str) -> bool:
    compact = re.sub(r"\s+", " ", text).strip()
    if compact in {
        "Simulate",
        "Alphas",
        "Learn",
        "Data",
        "Team",
        "Community",
        "Competitions",
        "IQC 2026",
        "Consultant program",
        "Refer a friend",
        "Notifications",
        "User menu",
    }:
        return True
    nav_words = r"(Simulate|Alphas|Learn|Data|Competitions|Team|Community|IQC|Consultant program|Refer a friend|Notifications|User menu)"
    return bool(len(compact) < 220 and re.fullmatch(rf"(?:{nav_words}|\s|\||\(\d+\))+", compact, re.I))


def normalize_message(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("\u00a0", " ")
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def dedupe_error_messages(messages: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for message in messages:
        normalized = normalize_message(message)
        if not normalized or looks_like_quality_result(normalized):
            continue
        key = re.sub(r"\s+", " ", normalized.lower())
        if key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    return result


def dedupe_plain_messages(messages: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for message in messages:
        normalized = normalize_message(message)
        key = re.sub(r"\s+", " ", normalized.lower())
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    return result


async def dismiss_cookie_banner(page: Page) -> None:
    selectors = [
        'button:has-text("Reject All")',
        'button:has-text("Accept All")',
        '[class*="cky" i] button[aria-label*="close" i]',
        '[id*="cookie" i] button[aria-label*="close" i]',
        '[class*="cookie" i] button[aria-label*="close" i]',
    ]
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            if not await locator.is_visible(timeout=250):
                continue
            text = await locator.inner_text(timeout=250)
            if re.search(r"\bSubmit\b|Apply|Reset|Customize Alpha Details|Settings", text, re.I):
                continue
            await locator.click(timeout=800, force=True)
            await asyncio.sleep(0.2)
            return
        except Exception:
            continue


async def dismiss_platform_toasts(page: Page) -> None:
    selectors = [
        '[class*="toast" i] button',
        '[class*="notification" i] button',
        '[class*="message" i] button',
        '[role="alert"] button[aria-label*="close" i]',
        '[class*="toast" i] button[aria-label*="close" i]',
        '[class*="notification" i] button[aria-label*="close" i]',
    ]
    for selector in selectors:
        try:
            count = await page.locator(selector).count()
            for index in range(min(count, 5)):
                button = page.locator(selector).nth(index)
                if await button.is_visible(timeout=300):
                    text = await button.inner_text(timeout=300)
                    if re.search(r"\bSubmit\b|Apply|Reset|Customize Alpha Details|Settings", text, re.I):
                        continue
                    await button.click(force=True, timeout=800)
        except Exception:
            continue


async def code_editor_is_visible(page: Page) -> bool:
    selectors = [
        ".monaco-editor textarea.inputarea",
        ".monaco-editor",
        ".cm-content",
        '[contenteditable="true"]',
    ]
    for selector in selectors:
        try:
            if await page.locator(selector).first.is_visible(timeout=500):
                return True
        except Exception:
            continue
    return False


class AutomationFlowError(RuntimeError):
    pass


async def ensure_code_editor_visible(page: Page) -> None:
    if await wait_for_simulate_workspace(page, timeout_seconds=120):
        logging.info("Code editor is visible after Simulate workspace load")
        return

    code_buttons = [
        'button:has-text("Code")',
        'button:has-text("CODE")',
        '[role="button"]:has-text("Code")',
        '[role="button"]:has-text("CODE")',
        'button:has-text("Edit")',
        '[role="button"]:has-text("Edit")',
        'button:has-text("编辑")',
        '[role="button"]:has-text("编辑")',
        'button:has-text("New Alpha")',
        '[role="button"]:has-text("New Alpha")',
        'button:has-text("New Simulation")',
        '[role="button"]:has-text("New Simulation")',
    ]
    for attempt in range(5):
        if await code_editor_is_visible(page):
            logging.info("Code editor is visible")
            return
        for selector in code_buttons:
            try:
                button = page.locator(selector).first
                if await button.is_visible(timeout=700):
                    text = await button.inner_text(timeout=500)
                    if re.search(r"\bSubmit\b|提交", text, re.I):
                        continue
                    await button.click(timeout=1500, force=True)
                    await asyncio.sleep(1)
                    if await code_editor_is_visible(page):
                        logging.info("Code editor is visible after clicking %s", selector)
                        return
                    break
            except Exception:
                continue
        if attempt == 0:
            try:
                await page.go_back(wait_until="domcontentloaded", timeout=15000)
                await wait_for_simulate_workspace(page, timeout_seconds=45)
            except Exception:
                pass
        else:
            await goto_page(page, SIMULATE_URL)
            await wait_for_simulate_workspace(page, timeout_seconds=60)
    body = await safe_body_text(page, timeout=5000)
    if not body.strip():
        logging.warning("Simulate page body is empty; reload before trying to recover editor")
        try:
            await page.reload(wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)
            if await code_editor_is_visible(page):
                logging.info("刷新后 Code editor 可见")
                return
        except Exception:
            pass
        body = await safe_body_text(page, timeout=5000)
    raise AutomationFlowError(
        "[AUTOMATION] 未能恢复到可编辑的 Simulate 代码编辑器；页面状态摘要："
        + re.sub(r"\s+", " ", body)[:500]
    )


async def wait_for_simulate_workspace(page: Page, timeout_seconds: int = 120) -> bool:
    deadline = time.time() + timeout_seconds
    last_log_at = 0.0
    while time.time() < deadline:
        if await code_editor_is_visible(page):
            return True
        if await simulate_form_hint_visible(page):
            return True
        loading = await visible_loading_indicator(page)
        body = await safe_body_text(page, timeout=3000)
        nav_only = looks_like_nav_only_page(body)
        now = time.time()
        if now - last_log_at >= 15:
            logging.info(
                "等待 Simulate 主内容加载：loading=%s nav_only=%s url=%s",
                loading,
                nav_only,
                page.url,
            )
            last_log_at = now
        if not loading and not nav_only and len(body.strip()) > 80:
            return False
        await asyncio.sleep(2)
    return await code_editor_is_visible(page)


async def simulate_form_hint_visible(page: Page) -> bool:
    selectors = [
        'input[name="name"]',
        'input[placeholder*="name" i]',
        'button:has-text("Simulate")',
        'button:has-text("Run")',
        '.editor-simulate',
        '[class*="simulate" i]',
    ]
    for selector in selectors:
        try:
            if await page.locator(selector).first.is_visible(timeout=400):
                return True
        except Exception:
            continue
    return False


def looks_like_nav_only_page(text: str) -> bool:
    compact = re.sub(r"\s+", " ", text or "").strip()
    if not compact:
        return True
    nav_terms = [
        "Simulate",
        "Alphas",
        "Learn",
        "Data",
        "Competitions",
        "Team",
        "Community",
        "Notifications",
        "User menu",
    ]
    if all(term in compact for term in ["Simulate", "Alphas", "Learn"]) and len(compact) < 260:
        return True
    stripped = compact
    for term in nav_terms:
        stripped = stripped.replace(term, "")
    stripped = re.sub(r"[\s()0-9|]+", "", stripped)
    return len(stripped) < 20


async def read_progress(page: Page) -> float | None:
    try:
        values = await page.evaluate(
            """() => {
                const normalize = text => String(text || '').replace(/\\s+/g, ' ').trim();
                const visible = el => {
                    const style = window.getComputedStyle(el);
                    const rect = el.getBoundingClientRect();
                    return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
                };
                const inGlobalNavigation = el => {
                    let node = el;
                    for (let depth = 0; node && depth < 8; depth += 1, node = node.parentElement) {
                        const attrs = [
                            node.tagName,
                            node.id || '',
                            String(node.className || ''),
                            node.getAttribute('role') || '',
                            node.getAttribute('aria-label') || '',
                            node.getAttribute('data-testid') || ''
                        ].join(' ');
                        const text = normalize(node.innerText || node.textContent || '');
                        if (/\\b(nav|navigation|sidebar|side-bar|menu|topbar|navbar|header)\\b/i.test(attrs) && text.length < 500) return true;
                    }
                    return false;
                };
                const editor = document.querySelector('.monaco-editor, .cm-editor, .cm-content, textarea.inputarea');
                const editorRect = editor ? editor.getBoundingClientRect() : null;
                const nearEditor = el => {
                    if (!editorRect) return false;
                    const rect = el.getBoundingClientRect();
                    return rect.top >= editorRect.top - 220 && rect.top <= editorRect.bottom + 360 &&
                        rect.left >= editorRect.left - 160 && rect.left <= editorRect.right + 420;
                };
                const relevantProgress = el => {
                    if (inGlobalNavigation(el)) return false;
                    let node = el;
                    for (let depth = 0; node && depth < 7; depth += 1, node = node.parentElement) {
                        const text = normalize(node.innerText || node.textContent || '');
                        const attrs = [
                            node.tagName,
                            node.id || '',
                            String(node.className || ''),
                            node.getAttribute('role') || '',
                            node.getAttribute('aria-label') || '',
                            node.getAttribute('data-testid') || ''
                        ].join(' ');
                        if (/tutorial/i.test(text + ' ' + attrs) && !/simulate|simulation/i.test(text + ' ' + attrs)) return false;
                        if (/simulate|simulation|backtest|editor|alpha-detail|result|summary|testing/i.test(text + ' ' + attrs)) return true;
                        if (/Simulations usually take|cancel the simulation|IS Summary|IS Testing Status|running|queued|calculating/i.test(text)) return true;
                    }
                    return nearEditor(el);
                };
                const selector = [
                    '[role="progressbar"]',
                    'progress',
                    '[aria-valuenow]',
                    '[class*="progress" i]'
                ].join(',');
                const values = [];
                for (const el of Array.from(document.querySelectorAll(selector)).slice(0, 80)) {
                    if (!visible(el) || !relevantProgress(el)) continue;
                    const text = `${el.innerText || el.textContent || ''} ${el.getAttribute('aria-valuenow') || ''}`;
                    for (const m of text.matchAll(/(\\d{1,3}(?:\\.\\d+)?)\\s*%/g)) values.push(Number(m[1]));
                    const aria = el.getAttribute('aria-valuenow');
                    const max = Number(el.getAttribute('aria-valuemax') || 100);
                    if (aria !== null && !Number.isNaN(Number(aria))) values.push(max && max !== 100 ? Number(aria) / max * 100 : Number(aria));
                    if (typeof el.value === 'number') {
                        const pmax = typeof el.max === 'number' && el.max ? el.max : 100;
                        values.push(pmax !== 100 ? el.value / pmax * 100 : el.value);
                    }
                }
                return values.filter(v => v >= 0 && v <= 100);
            }"""
        )
    except Exception:
        return None
    return max(values) if values else None


async def safe_body_text(page: Page, timeout: int = 10000) -> str:
    try:
        return await page.locator("body").inner_text(timeout=timeout)
    except Exception:
        return ""


async def capture_screenshot(page: Page, alpha_name: str, suffix: str) -> str:
    if is_io_degraded():
        return ""
    path = ITERATION_DIR / f"{alpha_name}_{suffix}_{now_ts()}.png"
    try:
        ITERATION_DIR.mkdir(parents=True, exist_ok=True)
        await page.screenshot(path=str(path), full_page=True)
        trim_old_files(ITERATION_DIR, "*.png", keep=500)
        return str(path)
    except Exception:
        logging.info("Failed to capture screenshot: %s", path, exc_info=True)
        return ""
