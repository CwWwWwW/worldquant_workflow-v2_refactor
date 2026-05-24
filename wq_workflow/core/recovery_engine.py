from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class RecoveryActionType(str, Enum):
    NONE = "none"
    ROLLBACK = "rollback"
    BRANCH_RESET = "branch_reset"
    DIVERSITY_INJECTION = "diversity_injection"
    SIMPLIFY_STRATEGY = "simplify_strategy"


@dataclass
class RecoveryAction:
    action: RecoveryActionType
    reason: str = ""
    target_node_id: str = ""


class RecoveryEngine:
    def __init__(self, fail_threshold: int = 3, hard_fail_threshold: int = 6) -> None:
        self.fail_threshold = fail_threshold
        self.hard_fail_threshold = hard_fail_threshold

    def recover(self, tree: object | None, fail_count: int, strategy: object | None = None) -> RecoveryAction:
        if fail_count <= self.fail_threshold:
            return RecoveryAction(RecoveryActionType.NONE)
        if fail_count >= self.hard_fail_threshold:
            return RecoveryAction(RecoveryActionType.BRANCH_RESET, "hard failure threshold reached")
        strategy_name = str(getattr(strategy, "name", strategy or "")).lower()
        if "diversity" in strategy_name:
            return RecoveryAction(RecoveryActionType.SIMPLIFY_STRATEGY, "diversity expansion failed repeatedly")
        if "turnover" in strategy_name:
            return RecoveryAction(RecoveryActionType.ROLLBACK, "turnover reduction branch failed repeatedly")
        return RecoveryAction(RecoveryActionType.DIVERSITY_INJECTION, "consecutive failures exceeded threshold")

