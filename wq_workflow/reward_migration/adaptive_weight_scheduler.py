from __future__ import annotations

from .migration_state import MigrationSnapshot, MigrationState, normalize_weights
from .population_health import PopulationHealthSnapshot
from .reward_stability_monitor import RewardStabilitySnapshot


class AdaptiveWeightScheduler:
    def __init__(
        self,
        *,
        max_step_up: float = 0.05,
        moderate_step_down: float = 0.10,
        severe_step_down: float = 0.25,
    ) -> None:
        self.max_step_up = max_step_up
        self.moderate_step_down = moderate_step_down
        self.severe_step_down = severe_step_down

    def next_weights(
        self,
        state: MigrationState,
        health: PopulationHealthSnapshot,
        stability: RewardStabilitySnapshot,
        current: MigrationSnapshot,
    ) -> tuple[float, float]:
        if state == MigrationState.SHADOW:
            return 1.0, 0.0
        if state == MigrationState.FULL_V2:
            state = MigrationState.LATE_HYBRID

        v2_weight = current.v2_weight
        if state == MigrationState.EARLY_HYBRID:
            v2_weight = max(v2_weight, 0.10)
        elif state == MigrationState.MID_HYBRID:
            v2_weight = max(v2_weight, 0.30)
        elif state == MigrationState.LATE_HYBRID:
            v2_weight = max(v2_weight, 0.60)
        elif state == MigrationState.ROLLBACK:
            v2_weight = min(v2_weight, 0.10)

        risk_flags = set(health.risk_flags) | set(stability.risk_flags)
        severe = bool(
            risk_flags
            & {
                "diversity_collapse",
                "correlation_explosion",
                "mutation_failure_spike",
                "population_survival_low",
                "reward_variance_explosion",
                "ranking_instability",
                "abnormal_reward_spikes",
            }
        )
        if severe:
            v2_weight = max(0.0, v2_weight - self.severe_step_down)
        elif risk_flags - {"insufficient_samples"}:
            v2_weight = max(0.0, v2_weight - self.moderate_step_down)
        elif health.healthy and stability.stable:
            v2_weight = min(_state_cap(state), v2_weight + self.max_step_up)

        return normalize_weights(1.0 - v2_weight, v2_weight, state)


def _state_cap(state: MigrationState) -> float:
    if state == MigrationState.EARLY_HYBRID:
        return 0.30
    if state == MigrationState.MID_HYBRID:
        return 0.60
    if state == MigrationState.LATE_HYBRID:
        return 0.85
    if state == MigrationState.ROLLBACK:
        return 0.10
    return 1.0
