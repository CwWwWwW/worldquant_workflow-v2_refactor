from __future__ import annotations

from typing import Any


async def run_legacy_orchestrator(ctx: Any, argv: list[str] | None = None) -> int:
    from wq_workflow import orchestrator

    return await orchestrator.main(argv)
