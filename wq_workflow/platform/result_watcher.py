from __future__ import annotations

from typing import Any


class PlatformResultWatcher:
    async def wait_for_result(self, page: Any, config: Any, **kwargs: Any) -> str:
        from wq_workflow.simulate import wait_for_backtest_finished

        return await wait_for_backtest_finished(page, config, **kwargs)
