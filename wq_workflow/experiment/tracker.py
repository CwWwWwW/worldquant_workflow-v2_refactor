from __future__ import annotations

from typing import Any

from .service import ExperimentService


class ExperimentTracker:
    """Small facade for tracking start/assignment/result without exposing storage."""

    def __init__(self, service: ExperimentService) -> None:
        self.service = service

    def record_start(self) -> dict[str, Any]:
        return self.service.startup_check()

    def bind_candidate(self, candidate_context: Any):
        return self.service.assign_candidate(candidate_context)

    def record_result(self, alpha_id: str, result_context: Any):
        return self.service.record_result(alpha_id, result_context)
