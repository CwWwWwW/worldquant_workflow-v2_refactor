#!/usr/bin/env python
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from wq_workflow.browser_ops import ensure_authenticated  # noqa: E402
from wq_workflow.browser_supervisor import BrowserSupervisor  # noqa: E402
from wq_workflow.config import load_config  # noqa: E402
from wq_workflow.platform_sc import wait_and_extract_platform_sc  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Live debug WorldQuant BRAIN platform Self-Correlation panel extraction.")
    parser.add_argument("--url", help="Existing WorldQuant BRAIN alpha result page URL.")
    parser.add_argument(
        "--use-current-page",
        action="store_true",
        help="Reserved non-destructive mode; this repository currently has no cross-process current-page handle.",
    )
    parser.add_argument("--timeout-seconds", type=int, default=90)
    parser.add_argument("--headless", action="store_true", help="Override config and run browser headless.")
    return parser.parse_args()


async def main_async() -> int:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if args.use_current_page and not args.url:
        print("[LivePlatformSC] use_current_page unsupported=true reason=no_cross_process_page_handle; pass --url instead")
        return 2
    if not args.url:
        print('[LivePlatformSC] error=missing_url usage=python tools/debug_platform_sc_live.py --url "https://platform.worldquantbrain.com/alpha/xxxx"')
        return 2

    config = load_config()
    if args.headless:
        config.headless = True

    supervisor = BrowserSupervisor(config)
    session = None
    try:
        await supervisor.start()
        session = await supervisor.new_alpha_session("platform_sc_live")
        page = session.page
        await ensure_authenticated(page, config, target_url=args.url)
        await page.wait_for_timeout(3000)
        if "/alphas/unsubmitted" in args.url or "/alphas/submitted" in args.url:
            picked = await pick_first_alpha_from_list(page)
            print(f"[LivePlatformSC] list_page_pick success={str(picked).lower()} url={page.url}")
        result = await wait_and_extract_platform_sc(page, timeout_seconds=args.timeout_seconds)
        print("[LivePlatformSC] result_json=" + json.dumps(result, ensure_ascii=False))
        return 0 if result.get("status") in {"complete", "missing", "timeout", "unknown"} else 1
    finally:
        if session is not None:
            await supervisor.close_session(session, persist_storage=False)
        await supervisor.close()


def main() -> int:
    return asyncio.run(main_async())


async def pick_first_alpha_from_list(page) -> bool:
    """Open the first visible alpha detail row from an alphas list page without changing online state."""
    selectors = [
        '.rt-tr:has-text("UNSUBMITTED")',
        '.rt-tr:has-text("SUBMITTED")',
        '[role="row"]:has-text("UNSUBMITTED")',
        '[role="row"]:has-text("SUBMITTED")',
    ]
    for _ in range(20):
        for selector in selectors:
            rows = page.locator(selector)
            try:
                count = await rows.count()
            except Exception:
                count = 0
            for index in range(count):
                row = rows.nth(index)
                try:
                    text = await row.inner_text(timeout=500)
                except Exception:
                    text = ""
                if "Fast Expression" not in text and "Regular" not in text:
                    continue
                try:
                    await row.scroll_into_view_if_needed(timeout=1000)
                except Exception:
                    pass
                try:
                    box = await row.bounding_box(timeout=1000)
                except Exception:
                    box = None
                if box:
                    await page.mouse.click(box["x"] + min(180, box["width"] / 2), box["y"] + box["height"] / 2)
                else:
                    await row.click(timeout=2000)
                await page.wait_for_timeout(3000)
                return True
        await page.wait_for_timeout(1000)
    return False


if __name__ == "__main__":
    raise SystemExit(main())
