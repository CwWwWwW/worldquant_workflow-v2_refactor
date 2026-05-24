from __future__ import annotations

import math
import random
from typing import Any

from ...candidate_pool import diversity_score
from ...mutation_engine import complexity_score
from ...safe_io import finite_float
from .authority import evolution_authority
from .lineage_value import LineageValueEstimator


class PopulationEngine:
    def __init__(
        self,
        value_estimator: LineageValueEstimator | None = None,
        repository: Any | None = None,
        config: Any | None = None,
    ) -> None:
        self.value_estimator = value_estimator or LineageValueEstimator()
        self.repository = repository
        self.config = config

    def score_overlay(
        self,
        candidate: dict[str, Any],
        population: list[dict[str, Any]] | None = None,
        lineage_history: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        population = [row for row in (population or []) if isinstance(row, dict)]
        alpha_id = str(candidate.get("alpha_id") or "")
        family = str(candidate.get("family") or candidate.get("behavior_family") or "legacy")
        reward = finite_float(candidate.get("reward"))
        diversity = finite_float(candidate.get("diversity_score"), 0.5, minimum=0.0, maximum=1.0)
        low_corr = 1.0 - finite_float(candidate.get("estimated_self_corr"), 0.0, minimum=0.0, maximum=1.0)
        robustness = _robustness(candidate)
        stability = _stability(candidate)
        family_rarity = _family_rarity(family, population)
        lineage_novelty = _lineage_novelty(candidate)
        long_term_value = self.value_estimator.estimate_future_reward(alpha_id, lineage_history or [])
        lineage_risk = round(1.0 - lineage_novelty, 6)
        survival_score = (
            0.30 * _normalize_reward(reward)
            + 0.20 * diversity
            + 0.15 * family_rarity
            + 0.15 * lineage_novelty
            + 0.10 * low_corr
            + 0.05 * robustness
            + 0.05 * stability
        )
        return {
            "survival_score": round(survival_score, 6),
            "diversity_bonus": round(diversity, 6),
            "family_rarity": round(family_rarity, 6),
            "lineage_novelty": round(lineage_novelty, 6),
            "lineage_risk": lineage_risk,
            "long_term_value": long_term_value,
            "low_corr_bonus": round(low_corr, 6),
            "robustness": round(robustness, 6),
            "stability": round(stability, 6),
            **evolution_authority(self.config, "population", active_decision=True),
        }

    def bootstrap_from_legacy(self, candidate_pool: Any | None = None, evolution_memory: Any | None = None, limit: int = 2000) -> int:
        if self.repository is None:
            return 0
        try:
            completed = str(self.repository.get_meta("legacy_full_import_completed", "")).strip().lower() in {"1", "true", "yes", "on"}
            if completed:
                if self.get_population(limit=1, active_only=False):
                    import logging

                    logging.info("EVOLUTION_BOOTSTRAP_SKIPPED_FULL_IMPORT_COMPLETED")
                    return 0
                import logging

                logging.info("EVOLUTION_BOOTSTRAP_EMERGENCY_EMPTY_POPULATION")
        except Exception:
            pass
        count = 0
        try:
            count += int(self.repository.bootstrap_population_from_legacy(limit=limit) or 0)
        except Exception:
            count += 0
        rows: list[dict[str, Any]] = []
        if candidate_pool is not None and hasattr(candidate_pool, "_read"):
            try:
                rows.extend([row for row in candidate_pool._read() if isinstance(row, dict)])
            except Exception:
                pass
        if evolution_memory is not None and hasattr(evolution_memory, "load_recent_history"):
            try:
                for row in evolution_memory.load_recent_history(limit=limit):
                    if not isinstance(row, dict):
                        continue
                    rows.append(
                        {
                            **row,
                            "alpha_id": row.get("alpha_id") or row.get("child_alpha"),
                            "expression": row.get("expression_after") or row.get("expression"),
                            "parent_ids": [row.get("parent_id") or row.get("parent_alpha")],
                            "mutation_history": [row],
                            "birth_source": "legacy_evolution_memory",
                        }
                    )
            except Exception:
                pass
        deduped = _dedupe_by_expression(rows)
        current = self.get_population(limit=max(1, int(getattr(self.config, "population_size", 80))), active_only=False)
        population = current + list(deduped.values())
        for row in deduped.values():
            row.setdefault("status", "active")
            row.setdefault("birth_source", "legacy_bootstrap")
            if not row.get("alpha_id"):
                row["alpha_id"] = f"legacy_bootstrap_{abs(hash(str(row.get('expression') or ''))) % 10_000_000}"
            if "survival_score" not in row:
                row.update(self.score_overlay(row, population=population, lineage_history=[]))
            try:
                self.repository.upsert_population_member(row)
                count += 1
            except Exception:
                continue
        return count

    def get_population(self, limit: int | None = None, active_only: bool = True) -> list[dict[str, Any]]:
        if self.repository is None:
            return []
        size = limit or int(getattr(self.config, "population_size", 80) or 80)
        try:
            return self.repository.list_population(limit=size, active_only=active_only)
        except Exception:
            return []

    def tournament_selection(self, population: list[dict[str, Any]] | None = None, k: int | None = None) -> dict[str, Any] | None:
        rows = [row for row in (population or self.get_population()) if isinstance(row, dict)]
        if not rows:
            return None
        sample_size = min(int(k or getattr(self.config, "population_tournament_k", 5) or 5), len(rows))
        sampled = random.sample(rows, sample_size)
        sampled.sort(key=_selection_tuple, reverse=True)
        return sampled[0] if sampled else None

    def select_parent(self, population: list[dict[str, Any]] | None = None) -> dict[str, Any] | None:
        return self.tournament_selection(population)

    def select_parent_pair(self, population: list[dict[str, Any]] | None = None) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        rows = population or self.get_population()
        if not rows:
            return None, None
        parent_a = self.tournament_selection(rows)
        parent_b = self.tournament_selection(rows)
        tries = 0
        while parent_a and parent_b and parent_a.get("alpha_id") == parent_b.get("alpha_id") and tries < 5:
            parent_b = self.tournament_selection(rows)
            tries += 1
        return parent_a, parent_b

    def update_candidate(self, candidate: dict[str, Any]) -> None:
        if self.repository is None or not isinstance(candidate, dict):
            return
        if "survival_score" not in candidate:
            candidate.update(self.score_overlay(candidate, population=self.get_population(), lineage_history=[]))
        if "complexity" not in candidate:
            candidate["complexity"] = complexity_score(str(candidate.get("expression") or candidate.get("code") or ""))
        self.repository.upsert_population_member(candidate)
        self.survival_trim()

    def survival_trim(self) -> None:
        if self.repository is None:
            return
        size = max(1, int(getattr(self.config, "population_size", 80) or 80))
        elite_size = max(0, int(getattr(self.config, "population_elite_size", 12) or 12))
        max_family_ratio = finite_float(getattr(self.config, "population_max_same_family_ratio", 0.35), 0.35, minimum=0.01, maximum=1.0)
        rows = self.get_population(limit=max(size * 4, size + 20), active_only=True)
        rows.sort(key=_selection_tuple, reverse=True)
        survivors: list[dict[str, Any]] = rows[: min(elite_size, len(rows))]
        survivor_ids = {str(row.get("alpha_id") or "") for row in survivors}
        family_counts: dict[str, int] = {}
        for row in survivors:
            family = str(row.get("family") or row.get("behavior_family") or "unknown")
            family_counts[family] = family_counts.get(family, 0) + 1
        family_cap = max(1, int(math.ceil(size * max_family_ratio)))
        for row in rows:
            alpha_id = str(row.get("alpha_id") or "")
            if alpha_id in survivor_ids:
                continue
            family = str(row.get("family") or row.get("behavior_family") or "unknown")
            if len(survivors) >= size:
                break
            if family_counts.get(family, 0) >= family_cap:
                continue
            survivors.append(row)
            survivor_ids.add(alpha_id)
            family_counts[family] = family_counts.get(family, 0) + 1
        for row in rows:
            alpha_id = str(row.get("alpha_id") or "")
            if alpha_id and alpha_id not in survivor_ids:
                self.repository.mark_population_status(alpha_id, "archived")
        self.repository.insert_generation_summary(self.compute_generation_summary(survivors))

    def compute_generation_summary(self, population: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        rows = [row for row in (population or self.get_population()) if isinstance(row, dict)]
        generation = 0
        if self.repository is not None:
            try:
                generation = int(self.repository.get_current_generation()) + 1
            except Exception:
                generation = 0
        best = max(rows, key=_selection_tuple) if rows else {}
        families: dict[str, int] = {}
        for row in rows:
            family = str(row.get("family") or row.get("behavior_family") or "unknown")
            families[family] = families.get(family, 0) + 1
        entropy = 0.0
        for count in families.values():
            p = count / max(1, len(rows))
            entropy -= p * math.log(p, 2) if p > 0 else 0.0
        diversity_values = [finite_float(row.get("diversity_score"), 0.0, minimum=0.0, maximum=1.0) for row in rows]
        return {
            "generation": generation,
            "population_size": len(rows),
            "best_alpha_id": str(best.get("alpha_id") or ""),
            "best_reward": finite_float(best.get("reward"), 0.0),
            "avg_reward": round(sum(finite_float(row.get("reward"), 0.0) for row in rows) / max(1, len(rows)), 6),
            "avg_survival_score": round(sum(finite_float(row.get("survival_score"), 0.0) for row in rows) / max(1, len(rows)), 6),
            "family_entropy": round(entropy, 6),
            "diversity_score": round(sum(diversity_values) / max(1, len(diversity_values)), 6),
        }


def _normalize_reward(value: float) -> float:
    return max(0.0, min(1.0, (finite_float(value) + 10.0) / 20.0))


def _family_rarity(family: str, population: list[dict[str, Any]]) -> float:
    if not population:
        return 1.0
    total = len(population)
    same = sum(1 for row in population if str(row.get("family") or row.get("behavior_family") or "legacy") == family)
    return max(0.0, min(1.0, 1.0 - same / max(total, 1)))


def _lineage_novelty(candidate: dict[str, Any]) -> float:
    depth = finite_float(candidate.get("lineage_depth"), 0.0, minimum=0.0)
    return round(1.0 / (1.0 + depth / 10.0), 6)


def _robustness(candidate: dict[str, Any]) -> float:
    metrics = candidate.get("metrics") if isinstance(candidate.get("metrics"), dict) else {}
    sharpe = abs(finite_float(metrics.get("sharpe")))
    fitness = abs(finite_float(metrics.get("fitness")))
    return max(0.0, min(1.0, (sharpe * 0.6 + fitness * 0.4) / 3.0))


def _stability(candidate: dict[str, Any]) -> float:
    metrics = candidate.get("metrics") if isinstance(candidate.get("metrics"), dict) else {}
    turnover = finite_float(metrics.get("turnover"), 0.0, minimum=0.0)
    if 0 < turnover <= 1.0:
        turnover *= 100.0
    return max(0.0, min(1.0, 1.0 - turnover / 100.0))


def _selection_tuple(row: dict[str, Any]) -> tuple[float, float, float, float]:
    return (
        finite_float(row.get("survival_score"), 0.0),
        finite_float(row.get("long_term_value"), 0.0),
        finite_float(row.get("reward", row.get("score", 0.0)), 0.0),
        finite_float(row.get("diversity_score"), 0.0),
    )


def _dedupe_by_expression(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        expression = str(row.get("expression") or row.get("code") or row.get("expression_after") or "")
        if not expression:
            continue
        key = "".join(expression.lower().split())
        clone = dict(row)
        try:
            clone.setdefault("diversity_score", diversity_score(clone, rows))
        except Exception:
            clone.setdefault("diversity_score", 0.5)
        previous = result.get(key)
        if previous is None or finite_float(clone.get("reward", clone.get("score", 0.0))) > finite_float(previous.get("reward", previous.get("score", 0.0))):
            result[key] = clone
    return result
