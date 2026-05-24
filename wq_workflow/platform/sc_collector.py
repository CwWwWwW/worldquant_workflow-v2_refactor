from __future__ import annotations

from typing import Any

from wq_workflow.core_types import PlatformSCResult


class PlatformSCCollector:
    def __init__(self, logger: Any, timeout: int = 90):
        self.logger = logger
        self.timeout = timeout

    async def collect(self, page: Any) -> PlatformSCResult:
        try:
            from wq_workflow.platform_sc import wait_and_extract_platform_sc

            try:
                result = await wait_and_extract_platform_sc(page, timeout_seconds=self.timeout)
            except TypeError:
                result = await wait_and_extract_platform_sc(page, timeout=self.timeout)
            return PlatformSCResult(
                status=str(result.get("status", "unknown")),
                max=result.get("max"),
                min=result.get("min"),
                abs_max=result.get("abs_max"),
                selector=str(result.get("selector", "")),
                elapsed=result.get("elapsed", result.get("elapsed_seconds")),
                text_hash=str(result.get("text_hash", result.get("raw_text_hash", ""))),
                raw_text_preview=str(result.get("text_preview", result.get("raw_text_preview", ""))),
                error=str(result.get("error", "")),
            )
        except Exception as exc:
            if self.logger:
                self.logger.warning("platform sc collection failed: %s", exc)
            return PlatformSCResult(status="error", error=str(exc))
