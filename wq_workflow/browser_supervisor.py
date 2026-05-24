from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from playwright.async_api import Browser, BrowserContext, Page, Playwright

from .browser_ops import launch_playwright_browser
from .failure_artifacts import start_context_trace, stop_context_trace
from .models import BASE_URL, WorkflowConfig
from .paths import COOKIE_FILE
from .recovery import collect_chromium_pids, kill_chromium_processes


@dataclass
class AlphaBrowserSession:
    context: BrowserContext
    page: Page


class BrowserSupervisor:
    def __init__(self, config: WorkflowConfig) -> None:
        self.config = config
        self.playwright: Playwright | None = None
        self.browser: Browser | None = None
        self._context_kwargs: dict[str, Any] = {}
        self._browser_pids: set[int] = set()

    async def start(self) -> None:
        if self.browser and self.browser.is_connected():
            return
        await self._launch_browser()

    async def _launch_browser(self) -> None:
        if self.playwright:
            try:
                await self.playwright.stop()
            except Exception:
                logging.info("Failed to stop stale Playwright instance", exc_info=True)
        before_pids = await collect_chromium_pids()
        self.playwright, self.browser = await launch_playwright_browser(self.config)
        after_pids = await collect_chromium_pids()
        self._browser_pids = after_pids - before_pids
        if self._browser_pids:
            logging.info("Tracked Playwright-launched browser pids=%s", sorted(self._browser_pids))
        else:
            logging.info("No distinct browser pids detected for this Playwright launch")
        self._context_kwargs = self.context_kwargs()

    def context_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {"viewport": {"width": 1920, "height": 1080}}
        if COOKIE_FILE.exists():
            kwargs["storage_state"] = str(COOKIE_FILE)
        return kwargs

    async def new_alpha_session(self, alpha_id: str) -> AlphaBrowserSession:
        await self.start()
        assert self.browser is not None
        context = await self.browser.new_context(**self._context_kwargs)
        try:
            try:
                await context.grant_permissions(["clipboard-read", "clipboard-write"], origin=BASE_URL)
            except Exception:
                logging.info("Clipboard permission grant failed for alpha context", exc_info=True)
            await start_context_trace(context)
            page = await context.new_page()
            page.set_default_timeout(30000)
            logging.info("Created isolated browser context/page for alpha_id=%s", alpha_id)
            return AlphaBrowserSession(context=context, page=page)
        except Exception:
            try:
                await context.close()
            except Exception:
                logging.info("Failed to close alpha context after session creation failure", exc_info=True)
            raise

    async def close_session(self, session: AlphaBrowserSession | None, *, persist_storage: bool = False) -> None:
        if not session:
            return
        try:
            if persist_storage:
                await session.context.storage_state(path=str(COOKIE_FILE))
        except Exception:
            logging.info("Failed to persist context storage", exc_info=True)
        try:
            await stop_context_trace(session.context)
        except Exception:
            logging.info("Failed to stop alpha context trace", exc_info=True)
        try:
            await session.context.close()
        except Exception:
            logging.info("Failed to close alpha context", exc_info=True)

    async def restart_browser(self) -> None:
        logging.warning("Restarting browser through BrowserSupervisor")
        await self.close_browser_only()
        await self._launch_browser()

    async def kill_and_restart_browser(self) -> None:
        logging.warning("Killing Chromium processes and restarting browser")
        await self.close_browser_only()
        await kill_chromium_processes(set(self._browser_pids))
        self._browser_pids = set()
        await self._launch_browser()

    async def close_browser_only(self) -> None:
        if not self.browser:
            return
        try:
            await self.browser.close()
        except Exception:
            logging.info("Failed to close browser", exc_info=True)
        self.browser = None

    async def close(self) -> None:
        await self.close_browser_only()
        if self.playwright:
            try:
                await self.playwright.stop()
            except Exception:
                logging.info("Failed to stop Playwright", exc_info=True)
        self.playwright = None
