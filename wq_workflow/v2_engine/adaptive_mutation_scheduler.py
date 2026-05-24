from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from ..mutation_engine import normalize_turnover
from ..safe_io import finite_float


BASE_MUTATION_WEIGHTS = {
    "trade_when_mutation": 0.25,
    "group_mutation": 0.25,
    "bucket_mutation": 0.15,
    "signal_replace": 0.15,
    "operator_replace": 0.10,
    "window_mutation": 0.10,
}


@dataclass(slots=True)
class MutationSchedule:
    weights: dict[str, float]
    similarity_limit: float
    mutation_strength: str
    recommended_mutations: list[str]
    family_policy: str
    phase: int = 6
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AdaptiveMutationScheduler:
    def __init__(self, *, phase: int = 6) -> None:
        self.phase = max(1, min(int(phase or 6), 6))

    def schedule(
        self,
        metrics: dict[str, float] | None,
        fingerprint: dict[str, Any] | None,
        estimated_self_corr: dict[str, Any] | float | None,
        lineage_depth: int = 0,
        exploration_pressure: float = 0.0,
    ) -> MutationSchedule:
        metrics = metrics or {}
        fingerprint = fingerprint or {}
        family = str(fingerprint.get("family") or "hybrid")
        fitness = finite_float(metrics.get("fitness"))
        turnover = normalize_turnover(metrics.get("turnover", 0.0))
        estimate = _estimated_value(estimated_self_corr)
        pressure = finite_float(exploration_pressure, minimum=0.0, maximum=1.0)
        similarity_limit = 0.85 if fitness > 1.0 else 0.75

        weights = dict(BASE_MUTATION_WEIGHTS)
        _apply_family_modifiers(weights, family)
        if turnover > 65:
            weights["window_mutation"] += 0.05
            weights["trade_when_mutation"] += 0.04
            weights["signal_replace"] = max(0.05, weights["signal_replace"] - 0.04)
        if estimate > similarity_limit:
            weights["trade_when_mutation"] += 0.08
            weights["group_mutation"] += 0.05
            weights["operator_replace"] = max(0.04, weights["operator_replace"] - 0.03)
        if lineage_depth >= 6 and fitness > 1.0:
            weights["signal_replace"] = max(0.06, weights["signal_replace"] - 0.05)
            weights["operator_replace"] = max(0.04, weights["operator_replace"] - 0.03)
            weights["bucket_mutation"] += 0.04
        if pressure > 0:
            weights = self.increase_random_mutation(weights, pressure)
            weights = self.increase_cross_family_mutation(weights, pressure)
            weights = self.increase_operator_diversity(weights, pressure)
            similarity_limit = max(0.60, similarity_limit - pressure * 0.10)

        normalized = _normalize(weights)
        recommended = [
            key
            for key, _value in sorted(normalized.items(), key=lambda item: item[1], reverse=True)
            if self._phase_allows(key)
        ]
        strength = "strong" if estimate > similarity_limit else "inherit" if fitness > 1.0 else "balanced"
        return MutationSchedule(
            weights=normalized,
            similarity_limit=similarity_limit,
            mutation_strength=strength,
            recommended_mutations=recommended,
            family_policy=_family_policy(family),
            phase=self.phase,
            metadata={
                "family": family,
                "fitness": round(fitness, 6),
                "turnover": round(turnover, 6),
                "estimated_self_corr": round(estimate, 6),
                "lineage_depth": int(lineage_depth or 0),
                "exploration_pressure": round(pressure, 6),
            },
        )

    def increase_random_mutation(self, weights: dict[str, float], pressure: float) -> dict[str, float]:
        adjusted = dict(weights)
        boost = finite_float(pressure, minimum=0.0, maximum=1.0) * 0.08
        adjusted["signal_replace"] = adjusted.get("signal_replace", 0.0) + boost * 0.45
        adjusted["window_mutation"] = adjusted.get("window_mutation", 0.0) + boost * 0.30
        adjusted["bucket_mutation"] = adjusted.get("bucket_mutation", 0.0) + boost * 0.25
        return adjusted

    def increase_cross_family_mutation(self, weights: dict[str, float], pressure: float) -> dict[str, float]:
        adjusted = dict(weights)
        boost = finite_float(pressure, minimum=0.0, maximum=1.0) * 0.12
        adjusted["group_mutation"] = adjusted.get("group_mutation", 0.0) + boost * 0.45
        adjusted["bucket_mutation"] = adjusted.get("bucket_mutation", 0.0) + boost * 0.30
        adjusted["trade_when_mutation"] = adjusted.get("trade_when_mutation", 0.0) + boost * 0.25
        return adjusted

    def increase_operator_diversity(self, weights: dict[str, float], pressure: float) -> dict[str, float]:
        adjusted = dict(weights)
        boost = finite_float(pressure, minimum=0.0, maximum=1.0) * 0.10
        adjusted["operator_replace"] = adjusted.get("operator_replace", 0.0) + boost * 0.50
        adjusted["signal_replace"] = adjusted.get("signal_replace", 0.0) + boost * 0.25
        adjusted["window_mutation"] = adjusted.get("window_mutation", 0.0) + boost * 0.25
        return adjusted

    def _phase_allows(self, mutation: str) -> bool:
        if self.phase <= 1:
            return False
        if self.phase == 2:
            return mutation in {"signal_replace", "operator_replace", "window_mutation"}
        if self.phase == 3:
            return mutation in {"trade_when_mutation", "group_mutation", "bucket_mutation", "window_mutation"}
        return True


def _apply_family_modifiers(weights: dict[str, float], family: str) -> None:
    if family == "momentum":
        weights["trade_when_mutation"] += 0.05
        weights["window_mutation"] += 0.04
    elif family == "mean_reversion":
        weights["group_mutation"] += 0.07
        weights["window_mutation"] += 0.03
    elif family in {"volatility", "event"}:
        weights["trade_when_mutation"] += 0.08
        weights["bucket_mutation"] += 0.03
    elif family == "group":
        weights["group_mutation"] += 0.10
        weights["bucket_mutation"] += 0.05
    elif family == "hybrid":
        weights["bucket_mutation"] += 0.03


def _normalize(weights: dict[str, float]) -> dict[str, float]:
    total = sum(max(0.0, value) for value in weights.values()) or 1.0
    return {key: round(max(0.0, value) / total, 6) for key, value in weights.items()}


def _estimated_value(value: dict[str, Any] | float | None) -> float:
    if isinstance(value, dict):
        return finite_float(value.get("estimated_self_corr"))
    return finite_float(value)


def _family_policy(family: str) -> str:
    policies = {
        "momentum": "preserve trend signal; prefer regime gating and delay/window changes",
        "mean_reversion": "preserve reversal signal; prefer decay and group neutralization",
        "volatility": "preserve volatility source; prefer active-regime filters",
        "event": "preserve event trigger; mutate trade_when and bucket exposure",
        "group": "preserve group logic; mutate group field and bucket range",
        "hybrid": "preserve strongest branch; diversify behavior before operators",
        "legacy": "use conservative behavior recording and fallback mutations",
    }
    return policies.get(family, policies["hybrid"])
