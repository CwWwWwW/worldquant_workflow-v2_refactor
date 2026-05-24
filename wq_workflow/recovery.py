from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import signal
from enum import Enum, auto
from typing import Any

from playwright.async_api import Browser, BrowserContext, Page


class RecoveryLevel(Enum):
    LEVEL_1_RELOAD_PAGE = auto()
    LEVEL_2_RECREATE_PAGE = auto()
    LEVEL_3_REBUILD_CONTEXT = auto()
    LEVEL_4_RESTART_BROWSER = auto()
    LEVEL_5_KILL_CHROMIUM = auto()


class RecoveryError(RuntimeError):
    pass


async def reload_page(page: Page) -> Page:
    await page.reload(wait_until="domcontentloaded", timeout=30000)
    return page


async def recreate_page(context: BrowserContext, page: Page | None = None) -> Page:
    if page and not page.is_closed():
        try:
            await page.close()
        except Exception:
            logging.info("Failed to close stale page during recovery", exc_info=True)
    new_page = await context.new_page()
    new_page.set_default_timeout(30000)
    return new_page


async def rebuild_context(
    browser: Browser,
    context: BrowserContext | None,
    *,
    context_kwargs: dict[str, Any],
) -> tuple[BrowserContext, Page]:
    if context:
        try:
            await context.close()
        except Exception:
            logging.info("Failed to close context during recovery", exc_info=True)
    new_context = await browser.new_context(**context_kwargs)
    page = await new_context.new_page()
    page.set_default_timeout(30000)
    return new_context, page


async def restart_browser(close_browser_coro, launch_browser_coro) -> Browser:
    await close_browser_coro()
    return await launch_browser_coro()


async def collect_chromium_pids() -> set[int]:
    if os.name == "nt":
        return await _collect_windows_chromium_pids()
    return await _collect_posix_chromium_pids()


async def _collect_windows_chromium_pids() -> set[int]:
    names = ["chrome.exe", "chromium.exe", "msedge.exe"]
    pids: set[int] = set()
    for name in names:
        result = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {name}", "/FO", "CSV", "/NH"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        )
        for line in result.stdout.splitlines():
            fields = [part.strip().strip('"') for part in line.split(",")]
            if len(fields) >= 2 and fields[0].lower() == name:
                try:
                    pids.add(int(fields[1]))
                except ValueError:
                    continue
    return pids


async def _collect_posix_chromium_pids() -> set[int]:
    pids: set[int] = set()
    for pattern in ["chromium", "chrome", "msedge"]:
        result = subprocess.run(
            ["pgrep", "-f", pattern],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        )
        for line in result.stdout.splitlines():
            try:
                pid = int(line.strip())
            except ValueError:
                continue
            if pid != os.getpid():
                pids.add(pid)
    return pids


async def kill_chromium_processes(pids: set[int] | None = None) -> None:
    if not pids:
        logging.warning("Level 5 recovery requested but no Playwright-launched Chromium PIDs were tracked; skipping broad browser kill")
        return

    if os.name == "nt":
        for pid in sorted(pids):
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        await asyncio.sleep(1)
        return

    for pid in sorted(pids):
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            continue
        except PermissionError:
            logging.info("No permission to kill tracked Chromium pid=%s", pid)
    await asyncio.sleep(1)
