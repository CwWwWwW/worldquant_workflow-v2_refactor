from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ..paths import ALPHA_LINEAGE_FILE, CANDIDATE_POOL_FILE
from ..safe_io import finite_float, safe_read_json
from memory.file_locks import lock_for_memory_path


MIN_HEALTH_SAMPLE_SIZE = 8


@dataclass(slots=True)
class PopulationHealthSnapshot:
    diversity_index: float = 1.0
    average_correlation: float = 0.0
    mutation_success_rate: float = 0.5
    reward_variance: float = 0.0
    lineage_entropy: float = 1.0
    selection_stability: float = 1.0
    population_survival_rate: float = 0.5
    reward_to_future_success_correlation: float = 0.0
    healthy: bool = False
    sample_count: int = 0
    risk_flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class PopulationHealthMonitor:
    def __init__(
        self,
        *,
        pool_path: Path = CANDIDATE_POOL_FILE,
        lineage_path: Path = ALPHA_LINEAGE_FILE,
        min_sample_size: int = MIN_HEALTH_SAMPLE_SIZE,
    ) -> None:
        self.pool_path = pool_path
        self.lineage_path = lineage_path
        self.min_sample_size = min_sample_size

    def evaluate(
        self,
        pool_rows: list[dict[str, Any]] | None = None,
        lineage_rows: list[dict[str, Any]] | None = None,
        reward_history: list[dict[str, Any]] | None = None,
    ) -> PopulationHealthSnapshot:
        pool = pool_rows if pool_rows is not None else _read_list(self.pool_path)
        lineage = lineage_rows if lineage_rows is not None else _read_list(self.lineage_path)
        history = reward_history or []
        sample_count = max(len(pool), len(lineage), len(history))

        diversity = _avg_field(pool, "diversity_score", default=1.0)
        average_correlation = _average_correlation(pool)
        mutation_success_rate = _mutation_success_rate(lineage)
        reward_variance = _variance([_float(row.get("reward")) for row in lineage[-80:]])
        lineage_entropy = _lineage_entropy(lineage)
        selection_stability = _selection_stability(history)
        survival_rate = _survival_rate(pool, lineage)
        future_corr = _reward_future_success_correlation(history, lineage)

        risk_flags: list[str] = []
        if sample_count < self.min_sample_size:
            risk_flags.append("insufficient_samples")
        if diversity < 0.30:
            risk_flags.append("diversity_collapse")
        if average_correlation > 0.82:
            risk_flags.append("correlation_explosion")
        if mutation_success_rate < 0.18 and sample_count >= self.min_sample_size:
            risk_flags.append("mutation_failure_spike")
        if reward_variance > 2.5:
            risk_flags.append("reward_variance_high")
        if lineage_entropy < 0.35 and sample_count >= self.min_sample_size:
            risk_flags.append("lineage_entropy_low")
        if selection_stability < 0.45 and sample_count >= self.min_sample_size:
            risk_flags.append("selection_unstable")
        if survival_rate < 0.20 and sample_count >= self.min_sample_size:
            risk_flags.append("population_survival_low")
        if future_corr < -0.10 and sample_count >= self.min_sample_size:
            risk_flags.append("reward_future_success_negative")

        hard_flags = set(risk_flags) - {"insufficient_samples"}
        healthy = sample_count >= self.min_sample_size and not hard_flags
        return PopulationHealthSnapshot(
            diversity_index=round(diversity, 6),
            average_correlation=round(average_correlation, 6),
            mutation_success_rate=round(mutation_success_rate, 6),
            reward_variance=round(reward_variance, 6),
            lineage_entropy=round(lineage_entropy, 6),
            selection_stability=round(selection_stability, 6),
            population_survival_rate=round(survival_rate, 6),
            reward_to_future_success_correlation=round(future_corr, 6),
            healthy=healthy,
            sample_count=sample_count,
            risk_flags=risk_flags,
        )


def _average_correlation(pool: list[dict[str, Any]]) -> float:
    values: list[float] = []
    for row in pool:
        for key in (
            "estimated_self_corr",
            "max_semantic_similarity",
            "structural_correlation",
            "return_correlation",
            "correlation_score",
        ):
            if key in row:
                value = _float(row.get(key))
                if key == "correlation_score":
                    value = max(0.0, 1.0 - value)
                values.append(max(0.0, min(1.0, value)))
                break
    if values:
        return sum(values) / len(values)
    diversities = [_float(row.get("diversity_score"), 1.0) for row in pool if "diversity_score" in row]
    if diversities:
        return max(0.0, min(1.0, 1.0 - (sum(diversities) / len(diversities))))
    return 0.0


def _mutation_success_rate(lineage: list[dict[str, Any]]) -> float:
    rows = lineage[-80:]
    if not rows:
        return 0.5
    successes = sum(1 for row in rows if row.get("passed") or _float(row.get("reward")) > 0)
    return successes / len(rows)


def _lineage_entropy(lineage: list[dict[str, Any]]) -> float:
    rows = lineage[-120:]
    if not rows:
        return 1.0
    counts: dict[str, int] = {}
    for row in rows:
        parent_id = str(row.get("parent_id") or row.get("alpha_id") or "unknown")
        counts[parent_id] = counts.get(parent_id, 0) + 1
    total = sum(counts.values())
    if total <= 1 or len(counts) <= 1:
        return 0.0 if total else 1.0
    entropy = -sum((count / total) * math.log(count / total) for count in counts.values())
    return entropy / math.log(len(counts))


def _selection_stability(history: list[dict[str, Any]]) -> float:
    if len(history) < 4:
        return 1.0
    recent = history[-12:]
    deltas = [_float(row.get("ranking_delta")) for row in recent if "ranking_delta" in row]
    if not deltas:
        return 1.0
    avg_delta = sum(abs(value) for value in deltas) / len(deltas)
    return max(0.0, min(1.0, 1.0 - avg_delta))


def _survival_rate(pool: list[dict[str, Any]], lineage: list[dict[str, Any]]) -> float:
    if pool:
        survived = sum(1 for row in pool if row.get("passed") or _float(row.get("reward")) > 0)
        return survived / len(pool)
    rows = lineage[-80:]
    if not rows:
        return 0.5
    survived = sum(1 for row in rows if row.get("passed") or _float(row.get("reward")) > 0)
    return survived / len(rows)


def _reward_future_success_correlation(history: list[dict[str, Any]], lineage: list[dict[str, Any]]) -> float:
    pairs: list[tuple[float, float]] = []
    for row in history[-100:]:
        if "v2_reward" in row and "future_success" in row:
            pairs.append((_float(row.get("v2_reward")), 1.0 if row.get("future_success") else 0.0))
    if len(pairs) < 8:
        rows = lineage[-100:]
        pairs = [(_float(row.get("reward")), 1.0 if row.get("passed") else 0.0) for row in rows]
    if len(pairs) < 8:
        return 0.0
    left = [item[0] for item in pairs]
    right = [item[1] for item in pairs]
    return _pearson(left, right)


def _avg_field(rows: list[dict[str, Any]], key: str, default: float) -> float:
    values = [_float(row.get(key), default) for row in rows if key in row]
    if not values:
        return default
    return sum(values) / len(values)


def _variance(values: list[float]) -> float:
    values = [finite_float(value) for value in values]
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    return sum((value - mean) ** 2 for value in values) / len(values)


def _pearson(left: list[float], right: list[float]) -> float:
    left = [finite_float(value) for value in left]
    right = [finite_float(value) for value in right]
    if len(left) != len(right) or len(left) < 2:
        return 0.0
    left_mean = sum(left) / len(left)
    right_mean = sum(right) / len(right)
    numerator = sum((a - left_mean) * (b - right_mean) for a, b in zip(left, right))
    left_norm = math.sqrt(sum((a - left_mean) ** 2 for a in left))
    right_norm = math.sqrt(sum((b - right_mean) ** 2 for b in right))
    if not left_norm or not right_norm:
        return 0.0
    return max(-1.0, min(1.0, numerator / (left_norm * right_norm)))


def _read_list(path: Path) -> list[dict[str, Any]]:
    with lock_for_memory_path(path):
        data = safe_read_json(path, [])
    return data if isinstance(data, list) else []


def _float(value: Any, default: float = 0.0) -> float:
    return finite_float(value, default)
