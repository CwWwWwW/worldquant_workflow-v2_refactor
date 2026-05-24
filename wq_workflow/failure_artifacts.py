from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from playwright.async_api import BrowserContext, Page

from .paths import FAILURE_DIR, TRACE_DIR, now_ts
from .safe_io import trim_old_files
from .storage import is_io_degraded


MAX_FAILURE_ARTIFACTS = 200
MAX_TRACE_ARTIFACTS = 100


@dataclass
class FailureArtifacts:
    screenshot: str = ""
    html: str = ""
    trace: str = ""


def _safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value or "unknown").strip("_")
    return cleaned[:120] or "unknown"


async def capture_failure_artifacts(
    page: Page | None,
    *,
    alpha_id: str,
    state: str,
    context: BrowserContext | None = None,
) -> FailureArtifacts:
    if is_io_degraded():
        if context:
            try:
                await context.tracing.stop()
            except Exception:
                pass
        return FailureArtifacts()
    FAILURE_DIR.mkdir(parents=True, exist_ok=True)
    TRACE_DIR.mkdir(parents=True, exist_ok=True)
    stem = f"{_safe_name(alpha_id)}_{_safe_name(state)}_{now_ts()}"
    artifacts = FailureArtifacts()

    if page and not page.is_closed():
        screenshot = FAILURE_DIR / f"{stem}.png"
        html = FAILURE_DIR / f"{stem}.html"
        try:
            await page.screenshot(path=str(screenshot), full_page=True)
            artifacts.screenshot = str(screenshot)
        except Exception:
            logging.info("Failed to capture failure screenshot", exc_info=True)
        try:
            html.write_text(await page.content(), encoding="utf-8")
            artifacts.html = str(html)
        except Exception:
            logging.info("Failed to capture failure html", exc_info=True)

    if context:
        trace = TRACE_DIR / f"{stem}.zip"
        try:
            await context.tracing.stop(path=str(trace))
            artifacts.trace = str(trace)
        except Exception:
            logging.info("Failed to stop Playwright trace", exc_info=True)

    _trim_artifacts()
    return artifacts


async def start_context_trace(context: BrowserContext) -> None:
    if is_io_degraded():
        return
    try:
        await context.tracing.start(screenshots=True, snapshots=False, sources=False)
    except Exception:
        logging.info("Failed to start Playwright trace", exc_info=True)


async def stop_context_trace(context: BrowserContext) -> None:
    if is_io_degraded():
        return
    try:
        await context.tracing.stop()
    except Exception:
        logging.info("Failed to stop Playwright trace", exc_info=True)


def _trim_artifacts() -> None:
    trim_old_files(FAILURE_DIR, "*.png", keep=MAX_FAILURE_ARTIFACTS)
    trim_old_files(FAILURE_DIR, "*.html", keep=MAX_FAILURE_ARTIFACTS)
    trim_old_files(TRACE_DIR, "*.zip", keep=MAX_TRACE_ARTIFACTS)
