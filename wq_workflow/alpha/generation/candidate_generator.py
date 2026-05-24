from __future__ import annotations

from typing import Any

from wq_workflow.core_types import CandidateDraft


class CandidateGenerator:
    def generate(self, expression: str = "", **metadata: Any) -> CandidateDraft:
        return CandidateDraft(expression=expression, generation_metadata=metadata, source=metadata.get("source", "refactored"))
