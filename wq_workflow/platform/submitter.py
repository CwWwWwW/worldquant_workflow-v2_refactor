from __future__ import annotations

from typing import Any


class PlatformSubmitter:
    async def run_backtest(self, page: Any, code: str, alpha_name: str, config: Any) -> Any:
        from wq_workflow.simulate import run_platform_backtest

        return await run_platform_backtest(page, code, alpha_name, config)
