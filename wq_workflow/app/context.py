from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AppContext:
    config: Any
    paths: Any
    logger: Any
    storage: Any = None
    repositories: Any = None
    candidate_pool: Any = None
    browser_factory: Any = None
    platform_services: dict[str, Any] = field(default_factory=dict)
    alpha_services: dict[str, Any] = field(default_factory=dict)
    evaluation_services: dict[str, Any] = field(default_factory=dict)
    learning_services: dict[str, Any] = field(default_factory=dict)
    workflow_services: dict[str, Any] = field(default_factory=dict)
    offline_services: dict[str, Any] = field(default_factory=dict)
    data_services: dict[str, Any] = field(default_factory=dict)
    strategy_services: dict[str, Any] = field(default_factory=dict)
    experiment_service: Any = None
    decision_snapshot_service: Any = None
    offline_replay_service: Any = None
    counterfactual_service: Any = None
    experiment_services: dict[str, Any] = field(default_factory=dict)
    monitoring_services: dict[str, Any] = field(default_factory=dict)
    legacy_adapters: dict[str, Any] = field(default_factory=dict)
    runtime_status: dict[str, Any] = field(default_factory=dict)

    def service(self, group: str, name: str, default: Any = None) -> Any:
        mapping = getattr(self, f"{group}_services", None)
        if isinstance(mapping, dict):
            return mapping.get(name, default)
        return default
