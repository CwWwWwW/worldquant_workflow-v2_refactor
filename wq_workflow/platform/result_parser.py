from __future__ import annotations

from typing import Any


class PlatformResultParser:
    def parse_metrics(self, text: str) -> dict[str, Any]:
        from wq_workflow.quality import extract_metrics

        return extract_metrics(text or "")
