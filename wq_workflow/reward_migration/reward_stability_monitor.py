from __future__ import annotations

import statistics
from dataclasses import asdict, dataclass, field
from typing import Any

from ..safe_io import finite_float


@dataclass(slots=True)
class RewardStabilitySnapshot:
    reward_variance: float = 0.0
    ranking_delta: float = 0.0
    spike_score: float = 0.0
    oscillation_score: float = 0.0
    stable: bool = True
    sample_count: int = 0
    risk_flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RewardStabilityMonitor:
    def __init__(
        self,
        *,
        max_reward_variance: float = 2.5,
        max_ranking_delta: float = 0.55,
        max_spike_score: float = 0.70,
        max_oscillation_score: float = 0.65,
        min_sample_size: int = 8,
    ) -> None:
        self.max_reward_variance = max_reward_variance
        self.max_ranking_delta = max_ranking_delta
        self.max_spike_score = max_spike_score
        self.max_oscillation_score = max_oscillation_score
        self.min_sample_size = min_sample_size

    def evaluate(self, shadow_history: list[dict[str, Any]] | None = None) -> RewardStabilitySnapshot:
        rows = (shadow_history or [])[-120:]
        sample_count = len(rows)
        legacy_rewards = [_float(row.get("legacy_reward")) for row in rows]
        v2_rewards = [_float(row.get("v2_reward")) for row in rows]
        ranking_deltas = [_float(row.get("ranking_delta")) for row in rows if "ranking_delta" in row]

        variance = _variance(v2_rewards)
        ranking_delta = sum(abs(value) for value in ranking_deltas) / len(ranking_deltas) if ranking_deltas else 0.0
        spike_score = _spike_score(v2_rewards, legacy_rewards)
        oscillation_score = _oscillation_score(v2_rewards)

        risk_flags: list[str] = []
        if sample_count < self.min_sample_size:
            risk_flags.append("insufficient_samples")
        if variance > self.max_reward_variance:
            risk_flags.append("reward_variance_explosion")
        if ranking_delta > self.max_ranking_delta:
            risk_flags.append("ranking_instability")
        if spike_score > self.max_spike_score:
            risk_flags.append("abnormal_reward_spikes")
        if oscillation_score > self.max_oscillation_score:
            risk_flags.append("reward_oscillation")
        stable = sample_count >= self.min_sample_size and not (set(risk_flags) - {"insufficient_samples"})
        return RewardStabilitySnapshot(
            reward_variance=round(variance, 6),
            ranking_delta=round(ranking_delta, 6),
            spike_score=round(spike_score, 6),
            oscillation_score=round(oscillation_score, 6),
            stable=stable,
            sample_count=sample_count,
            risk_flags=risk_flags,
        )


def _variance(values: list[float]) -> float:
    values = [finite_float(value) for value in values]
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    return sum((value - mean) ** 2 for value in values) / len(values)


def _spike_score(v2_rewards: list[float], legacy_rewards: list[float]) -> float:
    if len(v2_rewards) < 4:
        return 0.0
    diffs = [abs(v2 - legacy) for v2, legacy in zip(v2_rewards, legacy_rewards)]
    if not diffs:
        return 0.0
    median = statistics.median(diffs)
    if median <= 0:
        return 0.0 if max(diffs) <= 1.0 else 1.0
    spike_count = sum(1 for value in diffs if value > median * 4 and value > 1.0)
    return spike_count / len(diffs)


def _oscillation_score(values: list[float]) -> float:
    if len(values) < 5:
        return 0.0
    deltas = [values[index] - values[index - 1] for index in range(1, len(values))]
    signs = [1 if value > 0 else -1 if value < 0 else 0 for value in deltas]
    meaningful = [sign for sign in signs if sign != 0]
    if len(meaningful) < 4:
        return 0.0
    flips = sum(1 for index in range(1, len(meaningful)) if meaningful[index] != meaningful[index - 1])
    return flips / max(len(meaningful) - 1, 1)


def _float(value: Any) -> float:
    return finite_float(value)
