from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class WorkerState:
    worker_id: str
    alpha_id: str
    current_task: str
    runtime_seconds: float = 0.0
    restart_count: int = 0
    health: str = "IDLE"
    current_alpha: str = ""
    last_event_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class PopulationMetrics:
    count: int = 0
    diversity: float = 0.0
    correlation: float = 0.0
    mutation_success_rate: float = 0.0
    reward_stability: float = 0.0
    survival_rate: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class MigrationMetrics:
    state: str = "shadow"
    legacy_weight: float = 1.0
    v2_weight: float = 0.0
    rollback_count: int = 0
    reward_variance: float = 0.0
    diversity_stability: float = 0.0
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class WorkflowStatus:
    status: str = "IDLE"
    population_count: int = 0
    queue_size: int = 0
    pass_rate: float = 0.0
    reward_mode: str = "LEGACY"
    migration_state: str = "shadow"
    runtime_seconds: float = 0.0
    last_success_time: str = ""
    pid: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class LogLine:
    timestamp: str
    level: str
    source: str
    message: str
    path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class LogManagerStatus:
    progress: str = "idle"
    archive_size: int = 0
    integrity_status: str = "unknown"
    last_backup_time: str = ""
    active_operation: str = ""
    export_id: str = ""
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class DashboardSnapshot:
    updated_at: str
    workflow: WorkflowStatus = field(default_factory=WorkflowStatus)
    workers: list[WorkerState] = field(default_factory=list)
    population: PopulationMetrics = field(default_factory=PopulationMetrics)
    migration: MigrationMetrics = field(default_factory=MigrationMetrics)
    logs: list[LogLine] = field(default_factory=list)
    log_manager: LogManagerStatus = field(default_factory=LogManagerStatus)
    last_success: dict[str, Any] = field(default_factory=dict)
    source_mtimes: dict[str, float] = field(default_factory=dict)
    stale: bool = False
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "updated_at": self.updated_at,
            "workflow": self.workflow.to_dict(),
            "workers": [item.to_dict() for item in self.workers],
            "population": self.population.to_dict(),
            "migration": self.migration.to_dict(),
            "logs": [item.to_dict() for item in self.logs],
            "log_manager": self.log_manager.to_dict(),
            "last_success": self.last_success,
            "source_mtimes": self.source_mtimes,
            "stale": self.stale,
            "errors": self.errors,
        }
