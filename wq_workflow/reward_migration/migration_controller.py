from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from ..core.evolution import AdaptiveLegacyController
from ..paths import (
    MIGRATION_LOG_DIR,
    MIGRATION_METRICS_FILE,
    MIGRATION_STATE_FILE,
    REWARD_SHADOW_LOG_DIR,
)
from ..safe_io import atomic_write_json, append_jsonl, finite_float, read_jsonl_tail
from memory.file_locks import lock_for_memory_path
from .adaptive_weight_scheduler import AdaptiveWeightScheduler
from .migration_state import (
    MigrationSnapshot,
    MigrationState,
    MigrationStateStore,
    rollback_snapshot,
    transition,
)
from .population_health import PopulationHealthMonitor, PopulationHealthSnapshot
from .reward_stability_monitor import RewardStabilityMonitor, RewardStabilitySnapshot


@dataclass(slots=True)
class MigrationDecision:
    final_reward: float
    state: MigrationState
    legacy_weight: float
    v2_weight: float
    action: str
    reason: str
    health: PopulationHealthSnapshot
    stability: RewardStabilitySnapshot

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["state"] = self.state.value
        return payload


class MigrationController:
    def __init__(
        self,
        *,
        state_path: Path = MIGRATION_STATE_FILE,
        metrics_path: Path = MIGRATION_METRICS_FILE,
        shadow_log_dir: Path = REWARD_SHADOW_LOG_DIR,
        migration_log_dir: Path = MIGRATION_LOG_DIR,
        health_monitor: PopulationHealthMonitor | None = None,
        stability_monitor: RewardStabilityMonitor | None = None,
        scheduler: AdaptiveWeightScheduler | None = None,
        adaptive_controller: AdaptiveLegacyController | None = None,
        enable_adaptive_legacy: bool = True,
        min_hybrid_samples: int = 12,
        healthy_streak_to_advance: int = 3,
        full_takeover_streak: int = 8,
    ) -> None:
        self.store = MigrationStateStore(state_path)
        self.metrics_path = metrics_path
        self.shadow_log_dir = shadow_log_dir
        self.migration_log_dir = migration_log_dir
        self.health_monitor = health_monitor or PopulationHealthMonitor()
        self.stability_monitor = stability_monitor or RewardStabilityMonitor()
        self.scheduler = scheduler or AdaptiveWeightScheduler()
        self.adaptive_controller = adaptive_controller or AdaptiveLegacyController()
        self.enable_adaptive_legacy = enable_adaptive_legacy
        self.min_hybrid_samples = min_hybrid_samples
        self.healthy_streak_to_advance = healthy_streak_to_advance
        self.full_takeover_streak = full_takeover_streak
        self.shadow_log_dir.mkdir(parents=True, exist_ok=True)
        self.migration_log_dir.mkdir(parents=True, exist_ok=True)
        self.metrics_path.parent.mkdir(parents=True, exist_ok=True)

    def blend_reward(
        self,
        *,
        alpha_id: str,
        legacy_reward: float,
        v2_breakdown: Any,
        context: dict[str, Any] | None = None,
    ) -> MigrationDecision:
        context = context or {}
        legacy_reward = _float(legacy_reward)
        v2_reward = _breakdown_reward(v2_breakdown, legacy_reward)
        history = self._read_shadow_history(limit=160)
        current = self.store.load()
        health = self.health_monitor.evaluate(
            pool_rows=_list_or_none(context.get("pool_rows")),
            lineage_rows=_list_or_none(context.get("lineage_rows")),
            reward_history=history,
        )
        stability = self.stability_monitor.evaluate(history)
        current = self._with_streaks(current, health, stability)

        action = "shadow"
        reason = "v2 shadow observation"
        if self._should_rollback(health, stability):
            reason = self._rollback_reason(health, stability)
            if current.state == MigrationState.ROLLBACK:
                current.reason = reason
                action = "rollback_hold"
            else:
                current = rollback_snapshot(current, reason, severe=self._severe(health, stability))
                action = "rollback"
                reason = current.reason
        else:
            next_state = self._next_state(current, health, stability)
            if next_state != current.state:
                current = transition(current, next_state, f"migration advanced to {next_state.value}")
                action = "transition"
                reason = current.reason
            else:
                action = "observe" if current.state == MigrationState.SHADOW else "blend"
                reason = "state retained"

        legacy_weight, v2_weight = self._next_weights(current, health, stability, context)
        current = current.with_weights(legacy_weight, v2_weight, reason)
        current.sample_count = max(current.sample_count, health.sample_count, stability.sample_count)
        self.store.save(current)

        final_reward = self._effective_reward(legacy_reward, v2_reward, current)
        decision = MigrationDecision(
            final_reward=round(_reward_cap(final_reward), 6),
            state=current.state,
            legacy_weight=current.legacy_weight,
            v2_weight=current.v2_weight,
            action=action,
            reason=reason,
            health=health,
            stability=stability,
        )
        self._write_shadow_log(alpha_id, legacy_reward, v2_reward, decision, v2_breakdown, context)
        self._write_metrics(decision, current)
        if action in {"rollback", "transition"}:
            self._append_migration_log(alpha_id, legacy_reward, v2_reward, decision)
        return decision

    def rollback_to_legacy(self, reason: str = "manual rollback guard") -> MigrationSnapshot:
        snapshot = rollback_snapshot(self.store.load(), reason, severe=True)
        self.store.save(snapshot)
        self._append_event({"event": "rollback_to_legacy", "reason": reason, "state": snapshot.to_dict()})
        return snapshot

    def can_full_takeover(
        self,
        health: PopulationHealthSnapshot | None = None,
        stability: RewardStabilitySnapshot | None = None,
        snapshot: MigrationSnapshot | None = None,
    ) -> bool:
        return False

    def _effective_reward(self, legacy_reward: float, v2_reward: float, snapshot: MigrationSnapshot) -> float:
        legacy_reward = _float(legacy_reward)
        v2_reward = _float(v2_reward)
        if snapshot.state == MigrationState.SHADOW:
            return legacy_reward
        return _reward_cap(snapshot.legacy_weight * legacy_reward + snapshot.v2_weight * v2_reward)

    def _with_streaks(
        self,
        snapshot: MigrationSnapshot,
        health: PopulationHealthSnapshot,
        stability: RewardStabilitySnapshot,
    ) -> MigrationSnapshot:
        healthy = health.healthy and stability.stable
        snapshot.healthy_streak = snapshot.healthy_streak + 1 if healthy else 0
        snapshot.unstable_streak = 0 if healthy else snapshot.unstable_streak + 1
        return snapshot

    def _next_state(
        self,
        snapshot: MigrationSnapshot,
        health: PopulationHealthSnapshot,
        stability: RewardStabilitySnapshot,
    ) -> MigrationState:
        if snapshot.state == MigrationState.ROLLBACK:
            if snapshot.healthy_streak >= self.healthy_streak_to_advance:
                return MigrationState.SHADOW
            return MigrationState.ROLLBACK
        if not (health.healthy and stability.stable):
            return snapshot.state
        if health.sample_count < self.min_hybrid_samples:
            return snapshot.state
        if snapshot.state == MigrationState.SHADOW and snapshot.healthy_streak >= self.healthy_streak_to_advance:
            return MigrationState.EARLY_HYBRID
        if snapshot.state == MigrationState.EARLY_HYBRID and snapshot.healthy_streak >= self.healthy_streak_to_advance * 2:
            return MigrationState.MID_HYBRID
        if snapshot.state == MigrationState.MID_HYBRID and snapshot.healthy_streak >= self.healthy_streak_to_advance * 3:
            return MigrationState.LATE_HYBRID
        return snapshot.state

    def _next_weights(
        self,
        current: MigrationSnapshot,
        health: PopulationHealthSnapshot,
        stability: RewardStabilitySnapshot,
        context: dict[str, Any],
    ) -> tuple[float, float]:
        if current.state == MigrationState.SHADOW:
            return 1.0, 0.0
        if current.state == MigrationState.ROLLBACK:
            return self.scheduler.next_weights(current.state, health, stability, current)
        if not self.enable_adaptive_legacy:
            return self.scheduler.next_weights(current.state, health, stability, current)
        hybrid = self.adaptive_controller.compute_hybrid_reward(
            0.0,
            0.0,
            reward_future_corr=health.reward_to_future_success_correlation,
            lineage_entropy=health.lineage_entropy,
            rollback_count=current.rollback_count,
            mutation_success=health.mutation_success_rate,
            reward_variance=stability.reward_variance,
            template_diversity=_float(context.get("template_diversity"), health.diversity_index),
        )
        return _float(hybrid.get("legacy_weight"), 0.85), _float(hybrid.get("v2_weight"), 0.15)

    def _should_rollback(self, health: PopulationHealthSnapshot, stability: RewardStabilitySnapshot) -> bool:
        severe_flags = {
            "diversity_collapse",
            "correlation_explosion",
            "mutation_failure_spike",
            "population_survival_low",
            "reward_variance_explosion",
            "ranking_instability",
            "abnormal_reward_spikes",
        }
        flags = set(health.risk_flags) | set(stability.risk_flags)
        return bool(flags & severe_flags)

    def _severe(self, health: PopulationHealthSnapshot, stability: RewardStabilitySnapshot) -> bool:
        severe_flags = {"diversity_collapse", "correlation_explosion", "population_survival_low"}
        return bool((set(health.risk_flags) | set(stability.risk_flags)) & severe_flags)

    def _rollback_reason(self, health: PopulationHealthSnapshot, stability: RewardStabilitySnapshot) -> str:
        flags = sorted((set(health.risk_flags) | set(stability.risk_flags)) - {"insufficient_samples"})
        return "rollback triggered: " + ", ".join(flags or ["reward migration instability"])

    def _write_shadow_log(
        self,
        alpha_id: str,
        legacy_reward: float,
        v2_reward: float,
        decision: MigrationDecision,
        v2_breakdown: Any,
        context: dict[str, Any],
    ) -> None:
        payload = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "alpha_id": alpha_id,
            "legacy_reward": round(_float(legacy_reward), 6),
            "v2_reward": round(_float(v2_reward), 6),
            "final_reward": decision.final_reward,
            "state": decision.state.value,
            "legacy_weight": decision.legacy_weight,
            "v2_weight": decision.v2_weight,
            "action": decision.action,
            "reason": decision.reason,
            "ranking_delta": _ranking_delta(context),
            "template_success": bool(context.get("template_success")),
            "template_success_reason": str(context.get("template_success_reason") or ""),
            "v2_breakdown": _to_dict(v2_breakdown),
            "population_health": decision.health.to_dict(),
            "reward_stability": decision.stability.to_dict(),
        }
        stem = _safe_name(alpha_id or "unknown")
        path = self.shadow_log_dir / f"{stem}.json"
        jsonl = self.shadow_log_dir / "reward_shadow.jsonl"
        _safe_write_json(path, payload)
        _safe_append_jsonl(jsonl, payload)

    def _write_metrics(self, decision: MigrationDecision, snapshot: MigrationSnapshot) -> None:
        payload = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "current_state": decision.state.value,
            "legacy_weight": decision.legacy_weight,
            "v2_weight": decision.v2_weight,
            "population_health": decision.health.to_dict(),
            "rollback_count": snapshot.rollback_count,
            "reward_variance": decision.stability.reward_variance,
            "diversity_index": decision.health.diversity_index,
            "takeover_progress": snapshot.takeover_progress,
            "stability": decision.stability.to_dict(),
            "state": snapshot.to_dict(),
        }
        _safe_write_json(self.metrics_path, payload)

    def _append_migration_log(
        self,
        alpha_id: str,
        legacy_reward: float,
        v2_reward: float,
        decision: MigrationDecision,
    ) -> None:
        self._append_event(
            {
                "event": decision.action,
                "alpha_id": alpha_id,
                "legacy_reward": legacy_reward,
                "v2_reward": v2_reward,
                "decision": decision.to_dict(),
            }
        )

    def _append_event(self, payload: dict[str, Any]) -> None:
        payload = {"timestamp": datetime.now().isoformat(timespec="seconds"), **payload}
        _safe_append_jsonl(self.migration_log_dir / "migration_events.jsonl", payload)

    def _read_shadow_history(self, limit: int = 120) -> list[dict[str, Any]]:
        return read_jsonl_tail(self.shadow_log_dir / "reward_shadow.jsonl", limit=limit)


def _breakdown_reward(v2_breakdown: Any, fallback: float) -> float:
    if isinstance(v2_breakdown, dict):
        return _float(v2_breakdown.get("final_reward"), fallback)
    return _float(getattr(v2_breakdown, "final_reward", fallback), fallback)


def _ranking_delta(context: dict[str, Any]) -> float:
    if "ranking_delta" in context:
        return _float(context.get("ranking_delta"), 0.0)
    legacy_rank = context.get("legacy_rank")
    v2_rank = context.get("v2_rank")
    if legacy_rank is not None and v2_rank is not None:
        return min(1.0, abs(_float(legacy_rank) - _float(v2_rank)) / 20.0)
    return 0.0


def _list_or_none(value: Any) -> list[dict[str, Any]] | None:
    return value if isinstance(value, list) else None


def _to_dict(value: Any) -> Any:
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if hasattr(value, "__dict__"):
        return dict(value.__dict__)
    return value


def _safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value or "unknown").strip("_")
    return cleaned[:120] or "unknown"


def _safe_write_json(path: Path, payload: dict[str, Any]) -> None:
    try:
        with lock_for_memory_path(path):
            atomic_write_json(path, payload)
    except OSError:
        logging.info("Failed to write migration json: %s", path, exc_info=True)


def _safe_append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    try:
        append_jsonl(path, payload)
    except OSError:
        logging.info("Failed to append migration log: %s", path, exc_info=True)


def _float(value: Any, default: float = 0.0) -> float:
    return finite_float(value, default)


def _reward_cap(value: Any) -> float:
    return finite_float(value, 0.0, minimum=-10.0, maximum=10.0)
