from __future__ import annotations

from typing import Any

from .population_engine import PopulationEngine


class EvolutionScorer:
    def __init__(self, population_engine: PopulationEngine | None = None) -> None:
        self.population_engine = population_engine or PopulationEngine()

    def score_overlay(
        self,
        candidate: dict[str, Any],
        population: list[dict[str, Any]] | None = None,
        lineage_history: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        return self.population_engine.score_overlay(candidate, population=population, lineage_history=lineage_history)

    def compute_survival_score(
        self,
        candidate: dict[str, Any],
        population: list[dict[str, Any]] | None = None,
        lineage_history: list[dict[str, Any]] | None = None,
    ) -> float:
        overlay = self.score_overlay(candidate, population=population, lineage_history=lineage_history)
        return float(overlay.get("survival_score", 0.0) or 0.0)
