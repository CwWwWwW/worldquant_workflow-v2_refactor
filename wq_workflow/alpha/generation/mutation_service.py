from __future__ import annotations

from typing import Any


class MutationService:
    def mutate(self, expression: str, *args: Any, **kwargs: Any) -> str:
        try:
            from wq_workflow.mutation_engine import MutationPlanner
            _ = MutationPlanner
        except Exception:
            pass
        return expression
