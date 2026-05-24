from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from ..paths import MIGRATION_STATE_FILE
from ..safe_io import atomic_write_json, finite_float, safe_read_json
from memory.file_locks import lock_for_memory_path


class MigrationState(str, Enum):
    SHADOW = "shadow"
    EARLY_HYBRID = "early_hybrid"
    MID_HYBRID = "mid_hybrid"
    LATE_HYBRID = "late_hybrid"
    FULL_V2 = "full_v2"
    ROLLBACK = "rollback"


@dataclass(slots=True)
class MigrationSnapshot:
    state: MigrationState = MigrationState.SHADOW
    legacy_weight: float = 1.0
    v2_weight: float = 0.0
    rollback_count: int = 0
    takeover_progress: float = 0.0
    last_transition_at: str = ""
    reason: str = "initial shadow mode"
    healthy_streak: int = 0
    unstable_streak: int = 0
    sample_count: int = 0
    last_rollback_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["state"] = self.state.value
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "MigrationSnapshot":
        if not isinstance(payload, dict):
            return cls()
        state = _state(payload.get("state"))
        legacy_weight = _float(payload.get("legacy_weight"), 1.0)
        v2_weight = _float(payload.get("v2_weight"), 0.0)
        legacy_weight, v2_weight = normalize_weights(legacy_weight, v2_weight, state)
        return cls(
            state=state,
            legacy_weight=legacy_weight,
            v2_weight=v2_weight,
            rollback_count=max(0, _int(payload.get("rollback_count"), 0)),
            takeover_progress=max(0.0, min(1.0, _float(payload.get("takeover_progress"), v2_weight))),
            last_transition_at=str(payload.get("last_transition_at") or ""),
            reason=str(payload.get("reason") or ""),
            healthy_streak=max(0, _int(payload.get("healthy_streak"), 0)),
            unstable_streak=max(0, _int(payload.get("unstable_streak"), 0)),
            sample_count=max(0, _int(payload.get("sample_count"), 0)),
            last_rollback_at=str(payload.get("last_rollback_at") or ""),
        )

    def with_weights(self, legacy_weight: float, v2_weight: float, reason: str = "") -> "MigrationSnapshot":
        legacy_weight, v2_weight = normalize_weights(legacy_weight, v2_weight, self.state)
        return MigrationSnapshot(
            state=self.state,
            legacy_weight=legacy_weight,
            v2_weight=v2_weight,
            rollback_count=self.rollback_count,
            takeover_progress=v2_weight,
            last_transition_at=self.last_transition_at,
            reason=reason or self.reason,
            healthy_streak=self.healthy_streak,
            unstable_streak=self.unstable_streak,
            sample_count=self.sample_count,
            last_rollback_at=self.last_rollback_at,
        )


class MigrationStateStore:
    def __init__(self, path: Path = MIGRATION_STATE_FILE) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> MigrationSnapshot:
        with lock_for_memory_path(self.path):
            payload = safe_read_json(self.path, {})
        return MigrationSnapshot.from_dict(payload)

    def save(self, snapshot: MigrationSnapshot) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with lock_for_memory_path(self.path):
            atomic_write_json(self.path, snapshot.to_dict())


def transition(snapshot: MigrationSnapshot, state: MigrationState, reason: str) -> MigrationSnapshot:
    legacy_weight, v2_weight = default_weights_for_state(state, snapshot.legacy_weight, snapshot.v2_weight)
    now = datetime.now().isoformat(timespec="seconds")
    return MigrationSnapshot(
        state=state,
        legacy_weight=legacy_weight,
        v2_weight=v2_weight,
        rollback_count=snapshot.rollback_count,
        takeover_progress=v2_weight,
        last_transition_at=now,
        reason=reason,
        healthy_streak=snapshot.healthy_streak,
        unstable_streak=snapshot.unstable_streak,
        sample_count=snapshot.sample_count,
        last_rollback_at=snapshot.last_rollback_at,
    )


def rollback_snapshot(snapshot: MigrationSnapshot, reason: str, severe: bool = False) -> MigrationSnapshot:
    v2_weight = 0.0 if severe else max(0.0, snapshot.v2_weight - 0.25)
    legacy_weight = 1.0 - v2_weight
    now = datetime.now().isoformat(timespec="seconds")
    return MigrationSnapshot(
        state=MigrationState.ROLLBACK,
        legacy_weight=legacy_weight,
        v2_weight=v2_weight,
        rollback_count=snapshot.rollback_count + 1,
        takeover_progress=v2_weight,
        last_transition_at=now,
        reason=reason,
        healthy_streak=0,
        unstable_streak=snapshot.unstable_streak + 1,
        sample_count=snapshot.sample_count,
        last_rollback_at=now,
    )


def normalize_weights(legacy_weight: float, v2_weight: float, state: MigrationState) -> tuple[float, float]:
    if state == MigrationState.SHADOW:
        return 1.0, 0.0
    if state == MigrationState.FULL_V2:
        state = MigrationState.LATE_HYBRID
    legacy_weight = max(0.0, legacy_weight)
    v2_weight = max(0.0, v2_weight)
    total = legacy_weight + v2_weight
    if total <= 0:
        legacy_weight, v2_weight = default_weights_for_state(state, 1.0, 0.0)
        total = legacy_weight + v2_weight
    legacy = legacy_weight / total
    v2 = v2_weight / total
    if state not in {MigrationState.SHADOW, MigrationState.ROLLBACK}:
        legacy = max(0.15, min(0.85, legacy))
        v2 = 1.0 - legacy
    return round(legacy, 6), round(v2, 6)


def default_weights_for_state(
    state: MigrationState,
    current_legacy: float = 1.0,
    current_v2: float = 0.0,
) -> tuple[float, float]:
    if state == MigrationState.SHADOW:
        return 1.0, 0.0
    if state == MigrationState.EARLY_HYBRID:
        return normalize_weights(max(current_legacy, 0.9), max(current_v2, 0.1), MigrationState.EARLY_HYBRID)
    if state == MigrationState.MID_HYBRID:
        return normalize_weights(min(max(current_legacy, 0.45), 0.75), max(current_v2, 0.25), MigrationState.MID_HYBRID)
    if state == MigrationState.LATE_HYBRID:
        return normalize_weights(min(max(current_legacy, 0.15), 0.45), max(current_v2, 0.55), MigrationState.LATE_HYBRID)
    if state == MigrationState.FULL_V2:
        return default_weights_for_state(MigrationState.LATE_HYBRID, current_legacy, current_v2)
    if state == MigrationState.ROLLBACK:
        return normalize_weights(max(current_legacy, 0.9), min(current_v2, 0.1), MigrationState.ROLLBACK)
    return 1.0, 0.0


def _state(value: Any) -> MigrationState:
    if str(value).lower() == MigrationState.FULL_V2.value:
        return MigrationState.LATE_HYBRID
    try:
        return MigrationState(str(value))
    except ValueError:
        return MigrationState.SHADOW


def _float(value: Any, default: float) -> float:
    return finite_float(value, default)


def _int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
