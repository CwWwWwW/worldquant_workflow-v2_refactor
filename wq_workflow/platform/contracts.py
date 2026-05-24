from __future__ import annotations

from dataclasses import dataclass

from wq_workflow.core_types import CandidateDraft, PlatformSCResult, ServiceResult, SimulationResult, WorkflowError


@dataclass
class PlatformError(Exception):
    code: str
    message: str
    recoverable: bool = True

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


__all__ = ["CandidateDraft", "PlatformSCResult", "ServiceResult", "SimulationResult", "WorkflowError", "PlatformError"]
