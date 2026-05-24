from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from ...paths import TEMPLATE_POPULATION_LOG_FILE, TEMPLATE_STATS_FILE
from ...safe_io import append_jsonl, finite_float
from .versioned_memory import VersionedEvolutionMemory


class TemplatePopulationController:
    def __init__(
        self,
        path: Path = TEMPLATE_STATS_FILE,
        log_path: Path = TEMPLATE_POPULATION_LOG_FILE,
        *,
        share_threshold: float = 0.35,
        penalty_multiplier: float = 0.7,
    ) -> None:
        self.path = path
        self.log_path = log_path
        self.share_threshold = finite_float(share_threshold, 0.35, minimum=0.0, maximum=1.0)
        self.penalty_multiplier = finite_float(penalty_multiplier, 0.7, minimum=0.0, maximum=1.0)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._store = VersionedEvolutionMemory(self.path)

    def load_stats(self) -> dict[str, dict[str, Any]]:
        payload = self._store.load_data()
        return {str(key): self._normalize_stat(value) for key, value in payload.items() if isinstance(value, dict)}

    def flush(self) -> None:
        self._store.flush()

    def close(self) -> None:
        self._store.close()

    def update_template_stats(self, rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        rows = [row for row in rows if isinstance(row, dict)]
        counts: dict[str, int] = {}
        successes: dict[str, int] = {}
        correlations: dict[str, list[float]] = {}
        operators: dict[str, set[str]] = {}
        for row in rows:
            family = self._behavior_family(row)
            counts[family] = counts.get(family, 0) + 1
            if row.get("passed") or finite_float(row.get("reward")) > 0:
                successes[family] = successes.get(family, 0) + 1
            corr = self._correlation(row)
            if corr is not None:
                correlations.setdefault(family, []).append(corr)
            operator = str(row.get("mutation_type") or row.get("operator") or "")
            if operator:
                operators.setdefault(family, set()).add(operator)

        total = max(len(rows), 1)
        entropy = self._family_entropy(counts)
        dominant_share = max((count / total for count in counts.values()), default=0.0)
        stats: dict[str, dict[str, Any]] = {}
        for family, count in sorted(counts.items()):
            share = self.compute_population_share(count, total)
            success_rate = successes.get(family, 0) / max(count, 1)
            corr_values = correlations.get(family, [])
            avg_correlation = sum(corr_values) / len(corr_values) if corr_values else 0.0
            operator_diversity = min(1.0, len(operators.get(family, set())) / 6.0)
            pressure = self.compute_exploration_pressure(
                share,
                success_rate,
                avg_correlation,
                entropy=entropy,
                operator_diversity=operator_diversity,
            )
            stats[family] = {
                "population_share": round(share, 6),
                "success_rate": round(success_rate, 6),
                "avg_correlation": round(avg_correlation, 6),
                "family_entropy": round(entropy, 6),
                "dominant_share": round(dominant_share, 6),
                "operator_diversity": round(operator_diversity, 6),
                "exploration_pressure": round(pressure, 6),
            }
        self._save(stats)
        self._log("update_template_stats", {"stats": stats})
        return stats

    def compute_population_share(self, count: int, total: int) -> float:
        return max(0.0, min(1.0, max(0, int(count)) / max(int(total), 1)))

    def compute_template_penalty(self, template: str) -> float:
        return self.compute_family_penalty(template)

    def compute_family_penalty(self, behavior_family: str) -> float:
        stats = self.load_stats()
        share = finite_float(stats.get(behavior_family or "legacy", {}).get("population_share"))
        if share > self.share_threshold:
            return self.penalty_multiplier
        return 1.0

    def compute_exploration_pressure(
        self,
        population_share: float,
        success_rate: float,
        avg_correlation: float,
        *,
        entropy: float = 1.0,
        operator_diversity: float = 1.0,
    ) -> float:
        pressure = max(0.0, finite_float(population_share) - self.share_threshold)
        pressure += max(0.0, finite_float(avg_correlation) - 0.65) * 0.5
        pressure += max(0.0, 0.18 - finite_float(success_rate)) * 0.5
        pressure += max(0.0, 0.45 - finite_float(entropy, 1.0)) * 0.4
        pressure += max(0.0, 0.35 - finite_float(operator_diversity, 1.0)) * 0.3
        if population_share > self.share_threshold:
            pressure += 0.2
        return max(0.0, min(1.0, pressure))

    def apply_penalty(self, reward: float, template: str) -> tuple[float, dict[str, Any]]:
        family = template or "legacy"
        penalty = self.compute_family_penalty(family)
        adjusted = finite_float(reward) * penalty
        stats = self.load_stats().get(family, {})
        result = {
            "behavior_family": family,
            "template": family,
            "penalty_multiplier": penalty,
            "population_share": finite_float(stats.get("population_share")),
            "exploration_pressure": finite_float(stats.get("exploration_pressure")),
        }
        self._log("apply_penalty", {"reward": reward, "adjusted_reward": adjusted, **result})
        return round(adjusted, 6), result

    def template_diversity(self) -> float:
        stats = self.load_stats()
        if not stats:
            return 1.0
        shares = [finite_float(row.get("population_share")) for row in stats.values()]
        return round(1.0 - max(shares or [0.0]), 6)

    def increase_random_mutation(self, behavior_family: str = "") -> float:
        return round(self._pressure_for_family(behavior_family) * 0.25, 6)

    def increase_cross_family_mutation(self, behavior_family: str = "") -> float:
        return round(self._pressure_for_family(behavior_family) * 0.35, 6)

    def increase_operator_diversity(self, behavior_family: str = "") -> float:
        return round(self._pressure_for_family(behavior_family) * 0.30, 6)

    def pressure_for_family(self, behavior_family: str = "") -> float:
        return self._pressure_for_family(behavior_family)

    def _behavior_family(self, row: dict[str, Any]) -> str:
        return str(row.get("behavior_family") or row.get("template") or "legacy")

    def _correlation(self, row: dict[str, Any]) -> float | None:
        for key in ("estimated_self_corr", "max_semantic_similarity", "avg_correlation"):
            if key in row:
                return max(0.0, min(1.0, finite_float(row.get(key))))
        if "diversity_score" in row:
            return max(0.0, min(1.0, 1.0 - finite_float(row.get("diversity_score"), 1.0)))
        return None

    def _save(self, stats: dict[str, dict[str, Any]]) -> None:
        self._store.save_data({str(key): self._normalize_stat(value) for key, value in stats.items() if isinstance(value, dict)})

    def _pressure_for_family(self, behavior_family: str) -> float:
        stats = self.load_stats()
        if behavior_family and behavior_family in stats:
            return finite_float(stats[behavior_family].get("exploration_pressure"), minimum=0.0, maximum=1.0)
        if not stats:
            return 0.0
        return max(finite_float(row.get("exploration_pressure"), minimum=0.0, maximum=1.0) for row in stats.values())

    def _family_entropy(self, counts: dict[str, int]) -> float:
        import math

        total = sum(max(0, count) for count in counts.values())
        active = [count for count in counts.values() if count > 0]
        if total <= 1 or len(active) <= 1:
            return 0.0 if total else 1.0
        entropy = -sum((count / total) * math.log(count / total) for count in active)
        return max(0.0, min(1.0, entropy / math.log(len(active))))

    def _normalize_stat(self, stat: dict[str, Any]) -> dict[str, Any]:
        return {
            "population_share": finite_float(stat.get("population_share"), minimum=0.0, maximum=1.0),
            "success_rate": finite_float(stat.get("success_rate"), minimum=0.0, maximum=1.0),
            "avg_correlation": finite_float(stat.get("avg_correlation"), minimum=0.0, maximum=1.0),
            "family_entropy": finite_float(stat.get("family_entropy"), 1.0, minimum=0.0, maximum=1.0),
            "dominant_share": finite_float(stat.get("dominant_share"), minimum=0.0, maximum=1.0),
            "operator_diversity": finite_float(stat.get("operator_diversity"), 1.0, minimum=0.0, maximum=1.0),
            "exploration_pressure": finite_float(stat.get("exploration_pressure"), minimum=0.0, maximum=1.0),
        }

    def _log(self, event: str, payload: dict[str, Any]) -> None:
        append_jsonl(
            self.log_path,
            {
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "event": event,
                **payload,
            },
        )
