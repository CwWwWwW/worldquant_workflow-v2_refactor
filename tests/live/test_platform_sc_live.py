from __future__ import annotations

import os
import asyncio
import unittest
from pathlib import Path

from wq_workflow.browser_ops import goto_page
from wq_workflow.browser_supervisor import BrowserSupervisor
from wq_workflow.config import load_config
from wq_workflow.platform_sc import wait_and_extract_platform_sc


class PlatformSCLiveTests(unittest.TestCase):
    def test_platform_sc_live_extract_or_artifacts(self) -> None:
        if os.getenv("RUN_WQ_LIVE_TESTS") != "1":
            self.skipTest("set RUN_WQ_LIVE_TESTS=1 to run live WQ tests")
        if not os.getenv("WQ_ALPHA_URL"):
            self.skipTest("set WQ_ALPHA_URL to an existing alpha result page URL")
        asyncio.run(_run_live_check())


async def _run_live_check() -> None:
    alpha_url = os.getenv("WQ_ALPHA_URL")
    if not alpha_url:
        raise AssertionError("WQ_ALPHA_URL must be set by the test wrapper")

    config = load_config()
    supervisor = BrowserSupervisor(config)
    session = None
    try:
        await supervisor.start()
        session = await supervisor.new_alpha_session("platform_sc_live_pytest")
        await goto_page(session.page, alpha_url, timeout=60000, retries=1)
        result = await wait_and_extract_platform_sc(session.page, timeout_seconds=90, artifact_prefix="platform_sc_live_test")
    finally:
        if session is not None:
            await supervisor.close_session(session, persist_storage=False)
        await supervisor.close()

    artifacts = result.get("artifacts") if isinstance(result.get("artifacts"), dict) else {}
    assert artifacts.get("result_json") and Path(str(artifacts["result_json"])).exists()
    assert artifacts.get("page_screenshot") and Path(str(artifacts["page_screenshot"])).exists()
    assert artifacts.get("panel_text") and Path(str(artifacts["panel_text"])).exists()
    assert artifacts.get("panel_html") and Path(str(artifacts["panel_html"])).exists()

    if result.get("status") == "complete":
        assert result.get("selector")
        assert result.get("abs_max") is not None
    else:
        print(f"[LivePlatformSC] live test did not complete; status={result.get('status')} artifacts={artifacts}")


if __name__ == "__main__":
    unittest.main()
