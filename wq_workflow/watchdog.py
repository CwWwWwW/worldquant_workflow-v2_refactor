from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable
from typing import TypeVar

from playwright.async_api import Browser, Page

T = TypeVar("T")


class WatchdogTimeout(TimeoutError):
    def __init__(self, scope: str, timeout: float) -> None:
        super().__init__(f"{scope} timed out after {timeout}s")
        self.scope = scope
        self.timeout = timeout


class BrowserUnhealthy(RuntimeError):
    pass


async def step(scope: str, awaitable: Awaitable[T], timeout: float) -> T:
    started = time.monotonic()
    try:
        return await asyncio.wait_for(awaitable, timeout=timeout)
    except asyncio.TimeoutError as exc:
        raise WatchdogTimeout(scope, timeout) from exc
    finally:
        logging.debug("watchdog step finished scope=%s duration=%.2fs", scope, time.monotonic() - started)


async def alpha(alpha_id: str, awaitable: Awaitable[T], timeout: float = 25 * 60) -> T:
    return await step(f"alpha:{alpha_id}", awaitable, timeout)


async def js_heartbeat(page: Page, timeout: float = 5.0) -> float:
    value = await step("browser:js_heartbeat", page.evaluate("Date.now()"), timeout)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


async def browser_healthy(browser: Browser, page: Page | None = None, timeout: float = 5.0) -> bool:
    if not browser.is_connected():
        raise BrowserUnhealthy("browser websocket disconnected")
    if page is not None:
        if page.is_closed():
            raise BrowserUnhealthy("page closed")
        await js_heartbeat(page, timeout=timeout)
    return True


async def browser_watchdog_loop(
    browser_getter,
    page_getter,
    on_unhealthy,
    *,
    interval_seconds: float = 10.0,
    timeout: float = 5.0,
) -> None:
    while True:
        await asyncio.sleep(interval_seconds)
        browser = browser_getter()
        page = page_getter()
        if browser is None:
            continue
        try:
            await browser_healthy(browser, page, timeout=timeout)
        except Exception as exc:
            logging.warning("Browser watchdog detected unhealthy browser/page: %s", exc)
            await on_unhealthy(exc)
