from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from ...paths import SIDECAR_ADVISORY_LOG_FILE
from ...safe_io import append_jsonl
from .alpha_simulator import AlphaSimulator
from .authority import evolution_authority
from .evolution_policy import suggest_mutation_weights
from .population_engine import PopulationEngine


class SidecarContract:
    def __init__(
        self,
        *,
        log_path: Path = SIDECAR_ADVISORY_LOG_FILE,
        population_engine: PopulationEngine | None = None,
        simulator: AlphaSimulator | None = None,
        enabled: bool = True,
        config: Any | None = None,
    ) -> None:
        self.log_path = log_path
        self.population_engine = population_engine or PopulationEngine()
        self.simulator = simulator or AlphaSimulator()
        self.enabled = enabled
        self.config = config

    def pre_backtest(
        self,
        candidate: dict[str, Any],
        *,
        population: list[dict[str, Any]] | None = None,
        lineage_history: list[dict[str, Any]] | None = None,
        mutation_history: list[dict[str, Any]] | None = None,
        enable_population_overlay: bool = True,
        enable_policy_hint: bool = True,
        enable_simulator: bool = True,
    ) -> dict[str, Any]:
        annotations: dict[str, Any] = {}
        if enable_population_overlay:
            annotations["population_overlay"] = self.population_engine.score_overlay(
                candidate,
                population=population,
                lineage_history=lineage_history,
            )
        if enable_policy_hint:
            annotations["mutation_weights_hint"] = suggest_mutation_weights(mutation_history or lineage_history or [])
        if enable_simulator:
            annotations["simulator_observation"] = self.simulator.evaluate(candidate)
        payload = self._annotation("pre_backtest", candidate, annotations)
        self._record(payload)
        return payload

    def post_backtest(
        self,
        candidate: dict[str, Any],
        *,
        metrics: dict[str, Any] | None = None,
        quality_passed: bool = False,
        template_success: bool = False,
    ) -> dict[str, Any]:
        annotations = {
            "observed_metrics": metrics or {},
            "quality_passed": bool(quality_passed),
            "template_success": bool(template_success),
            **evolution_authority(self.config, "sidecar_post", active_decision=False),
        }
        payload = self._annotation("post_backtest", candidate, annotations)
        self._record(payload)
        return payload

    def _annotation(self, phase: str, candidate: dict[str, Any], annotations: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "version": "1.2.0",
            "mode": "sidecar_advisory",
            "phase": phase,
            "alpha_id": str(candidate.get("alpha_id") or candidate.get("alpha_name") or ""),
            "expression_fingerprint": _fingerprint(str(candidate.get("expression") or candidate.get("code") or "")),
            "annotations": annotations,
            **evolution_authority(self.config, f"sidecar_{phase}", active_decision=False),
        }
        payload["event_id"] = _event_id(payload)
        return payload

    def _record(self, payload: dict[str, Any]) -> None:
        if not self.enabled:
            return
        append_jsonl(self.log_path, payload)


def _fingerprint(expression: str) -> str:
    normalized = "".join((expression or "").lower().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def _event_id(payload: dict[str, Any]) -> str:
    text = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:20]
