from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ...paths import EVOLUTION_LOG_DIR
from ...safe_io import finite_float
from ...storage import get_storage_manager
from ...storage.evolution_repository import EvolutionDBRepository
from ...storage.legacy_full_importer import LegacyFullImporter
from .alpha_graph import AlphaGraph
from .alpha_simulator import AlphaSimulator
from .authority import evolution_authority
from .crossover_engine import ASTCrossover
from .evolution_policy import EvolutionPolicy
from .evolution_scorer import EvolutionScorer
from .lineage_value import LineageValueEstimator
from .population_engine import PopulationEngine


EVOLUTION_EVENT_LOG_FILE = EVOLUTION_LOG_DIR / "evolution_events.jsonl"


class EvolutionOrchestrator:
    def __init__(self, config: Any, storage_manager: Any | None = None) -> None:
        self.config = config
        self.enabled = bool(getattr(config, "enable_sidecar_evolution", False))
        self.experimental = bool(getattr(config, "enable_experimental_evolution_decisions", False))
        self.storage = storage_manager or get_storage_manager()
        self.repo: EvolutionDBRepository | None = None
        if self.enabled and getattr(self.storage, "mode", "") != "jsonl_only":
            try:
                self.repo = EvolutionDBRepository(self.storage._connection())
            except Exception:
                logging.info("Evolution repository initialization failed", exc_info=True)
                self.repo = None
        self.lineage_value = LineageValueEstimator(repository=self.repo, config=config)
        self.population = PopulationEngine(value_estimator=self.lineage_value, repository=self.repo, config=config)
        self.policy = EvolutionPolicy(repository=self.repo, config=config)
        self.scorer = EvolutionScorer(self.population)
        self.graph = AlphaGraph(repository=self.repo)
        self.crossover = ASTCrossover(
            config=config,
            random_seed=getattr(config, "crossover_random_seed", None),
            graph=self.graph,
        )
        self.simulator = AlphaSimulator(
            low_confidence_threshold=float(getattr(config, "simulator_low_confidence_threshold", 0.2)),
            skip_threshold=float(getattr(config, "simulator_skip_threshold", 0.18)),
            never_skip_if_parent_reward_above=float(getattr(config, "simulator_never_skip_if_parent_reward_above", 1.0)),
            skip_enabled=bool(getattr(config, "simulator_skip_enabled", True)),
        )

    def bootstrap(self, candidate_pool: Any, evolution_memory: Any) -> None:
        if not self.enabled or self.repo is None:
            return
        self.record_event("EVOLUTION_BOOTSTRAP_START", {})
        try:
            if bool(getattr(self.config, "legacy_full_import_enabled", True)):
                import_stats = LegacyFullImporter(self.repo, self.storage, self.config).run_once(
                    candidate_pool=candidate_pool,
                    evolution_memory=evolution_memory,
                )
                self.record_event("EVOLUTION_LEGACY_FULL_IMPORT", import_stats)
            count = self.population.bootstrap_from_legacy(candidate_pool=candidate_pool, evolution_memory=evolution_memory)
            self.record_event("EVOLUTION_BOOTSTRAP_DONE", {"count": count})
            self.record_storage_health()
        except Exception:
            logging.info("Evolution bootstrap skipped", exc_info=True)
            self.record_event("EVOLUTION_FALLBACK_LEGACY_PATH", {"phase": "bootstrap"})

    def choose_parents(self, fallback_parent: dict[str, Any] | None) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        if not self.enabled or not self.experimental or not bool(getattr(self.config, "enable_population_engine", False)):
            return fallback_parent, None
        try:
            parent_a, parent_b = self.population.select_parent_pair()
            parent_a = parent_a or fallback_parent
            self.record_event(
                "EVOLUTION_PARENT_SELECTED",
                {
                    "parent_a": (parent_a or {}).get("alpha_id"),
                    "parent_b": (parent_b or {}).get("alpha_id"),
                },
            )
            self._write_decision(
                {
                    "generation": self._current_generation(),
                    "decision_type": "parent_selection",
                    "parent_a": (parent_a or {}).get("alpha_id"),
                    "parent_b": (parent_b or {}).get("alpha_id"),
                    "action_type": "parent_selection",
                    "action_name": "tournament_pair",
                    "raw_payload": evolution_authority(self.config, "parent_selection", active_decision=True),
                }
            )
            return parent_a, parent_b
        except Exception:
            logging.info("Evolution parent selection fallback", exc_info=True)
            self.record_event("EVOLUTION_FALLBACK_LEGACY_PATH", {"phase": "parent_selection"})
            return fallback_parent, None

    def choose_mutation(self, allowed_mutations: list[str], context: dict[str, Any]) -> tuple[str | None, dict[str, float]]:
        if (
            not self.enabled
            or not self.experimental
            or not bool(getattr(self.config, "enable_evolution_policy", False))
        ):
            return None, {}
        try:
            action, weights = self.policy.select_action("mutation", allowed_mutations, context)
            self.record_event(
                "EVOLUTION_POLICY_WEIGHTS",
                {
                    "action_type": "mutation",
                    "weights": weights,
                    "selected_action": action,
                    **evolution_authority(self.config, "policy", active_decision=True),
                },
            )
            self.record_event("EVOLUTION_MUTATION_SELECTED", {"action": action})
            self._write_decision(
                {
                    "generation": self._current_generation(),
                    "decision_type": "mutation_selection",
                    "action_type": "mutation",
                    "action_name": action or "",
                    "context_key": self.policy.context_key(context),
                    "weights": weights,
                    "selected_weight": weights.get(action or "", 0.0),
                    "raw_payload": evolution_authority(self.config, "policy", active_decision=True),
                }
            )
            return action, weights
        except Exception:
            logging.info("Evolution mutation policy fallback", exc_info=True)
            self.record_event("EVOLUTION_FALLBACK_LEGACY_PATH", {"phase": "mutation_policy"})
            return None, {}

    def maybe_make_crossover_candidate(
        self,
        parent_a: dict[str, Any] | None,
        parent_b: dict[str, Any] | None,
        context: dict[str, Any],
    ) -> dict[str, Any] | None:
        if not self.enabled or not self.experimental or not bool(getattr(self.config, "enable_crossover", False)):
            return None
        try:
            action, weights = self.policy.select_action("evolution_mode", ["crossover", "mutation", "random_seed"], context)
            attempt_payload = {
                "parent_a": (parent_a or {}).get("alpha_id"),
                "parent_b": (parent_b or {}).get("alpha_id"),
                "action": action,
                "weights": weights,
                **evolution_authority(self.config, "crossover", active_decision=True),
            }
            self.record_event("EVOLUTION_CROSSOVER_ATTEMPT", attempt_payload)
            self._write_decision(
                {
                    "generation": self._current_generation(),
                    "decision_type": "crossover_attempt",
                    "parent_a": (parent_a or {}).get("alpha_id"),
                    "parent_b": (parent_b or {}).get("alpha_id"),
                    "action_type": "evolution_mode",
                    "action_name": action or "",
                    "context_key": self.policy.context_key(context),
                    "weights": weights,
                    "selected_weight": weights.get(action or "", 0.0),
                    "raw_payload": attempt_payload,
                }
            )
            if action != "crossover":
                payload = {
                    "action": action,
                    "weights": weights,
                    "fallback_to": "mutation",
                    "reason": "random_seed_generator_unavailable" if action == "random_seed" else "policy_selected_mutation",
                    **evolution_authority(self.config, "crossover", active_decision=True),
                }
                self.record_event("EVOLUTION_CROSSOVER_FALLBACK", payload)
                self._write_decision(
                    {
                        "generation": self._current_generation(),
                        "decision_type": "crossover_fallback",
                        "parent_a": (parent_a or {}).get("alpha_id"),
                        "parent_b": (parent_b or {}).get("alpha_id"),
                        "action_type": "evolution_mode",
                        "action_name": action or "",
                        "context_key": self.policy.context_key(context),
                        "weights": weights,
                        "selected_weight": weights.get(action or "", 0.0),
                        "raw_payload": payload,
                    }
                )
                return None
            candidate = self.crossover.maybe_crossover(parent_a, parent_b, context)
            if candidate:
                candidate["policy_weights"] = weights
                self.record_event("EVOLUTION_CROSSOVER_SUCCESS", {"parent_ids": candidate.get("parent_ids"), **evolution_authority(self.config, "crossover", active_decision=True)})
                self._write_decision(
                    {
                        "generation": self._current_generation(),
                        "decision_type": "crossover_success",
                        "parent_a": (parent_a or {}).get("alpha_id"),
                        "parent_b": (parent_b or {}).get("alpha_id"),
                        "action_type": "crossover",
                        "action_name": "crossover",
                        "context_key": self.policy.context_key(context),
                        "weights": weights,
                        "selected_weight": weights.get("crossover", 0.0),
                        "raw_payload": {"candidate": candidate, **evolution_authority(self.config, "crossover", active_decision=True)},
                    }
                )
            else:
                self.record_event("EVOLUTION_CROSSOVER_FALLBACK", {"reason": "crossover_engine_returned_none"})
                self._update_policy("evolution_mode", "crossover", -0.02, False, context)
            return candidate
        except Exception:
            logging.info("Evolution crossover fallback", exc_info=True)
            self.record_event("EVOLUTION_CROSSOVER_FALLBACK", {"phase": "exception"})
            self._update_policy("evolution_mode", "crossover", -0.02, False, context)
            return None

    def before_backtest(self, candidate: dict[str, Any], context: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
        if not self.enabled or not bool(getattr(self.config, "enable_alpha_simulator", False)):
            return False, {}
        try:
            skip, observation = self.simulator.should_skip(candidate, context=context, experimental=self.experimental)
            authority = evolution_authority(self.config, "simulator", active_decision=True)
            observation.update({key: observation.get(key, value) for key, value in authority.items()})
            payload = {**candidate, **observation}
            self._write_simulator_observation(payload)
            self._write_decision(
                {
                    "generation": self._current_generation(),
                    "alpha_id": candidate.get("alpha_id"),
                    "candidate_alpha_id": candidate.get("alpha_id"),
                    "decision_type": "simulator_skip" if skip else "simulator_observation",
                    "action_type": "simulator_skip",
                    "action_name": "skip" if skip else "continue",
                    "simulator_score": observation.get("simulator_score", 0.0),
                    "skipped": skip,
                    "skipped_reason": observation.get("skipped_reason", ""),
                    "raw_payload": {"candidate": candidate, "observation": observation, **authority},
                }
            )
            if skip:
                self._update_policy(
                    "simulator_skip",
                    str(observation.get("skipped_reason") or "skip"),
                    -0.05,
                    False,
                    context,
                )
            self.record_event("EVOLUTION_SIMULATOR_SKIP" if skip else "EVOLUTION_SIMULATOR_OBSERVATION", payload)
            return skip, observation
        except Exception:
            logging.info("Evolution simulator fallback", exc_info=True)
            self.record_event("EVOLUTION_FALLBACK_LEGACY_PATH", {"phase": "simulator"})
            return False, {}

    def after_backtest(
        self,
        candidate: dict[str, Any],
        result: Any,
        reward_payload: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        if not self.enabled:
            return {}
        candidate = dict(candidate or {})
        reward_payload = dict(reward_payload or {})
        context = dict(context or {})
        overlay: dict[str, Any] = {}
        try:
            reward = finite_float(reward_payload.get("reward", reward_payload.get("final_reward", 0.0)), 0.0)
            success = bool(reward_payload.get("success") or reward_payload.get("passed") or candidate.get("passed"))
            metrics = candidate.get("metrics") if isinstance(candidate.get("metrics"), dict) else {}
            if not metrics and isinstance(reward_payload.get("metrics"), dict):
                metrics = dict(reward_payload.get("metrics") or {})
            candidate["reward"] = reward
            candidate["metrics"] = metrics
            try:
                population = self.population.get_population() if self.population else []
                overlay = self.scorer.score_overlay(candidate, population=population, lineage_history=[])
            except Exception:
                logging.info("Evolution survival scoring skipped", exc_info=True)
                overlay = {}
            enriched = {**candidate, **overlay, "reward": reward, "metrics": metrics}
            alpha_id = str(enriched.get("alpha_id") or "")
            mutation_type = str(enriched.get("mutation_type") or "")
            candidate_source = str(enriched.get("candidate_source") or enriched.get("source") or "")
            parent_reward = finite_float(enriched.get("parent_reward", 0.0), 0.0)
            reward_delta = reward - parent_reward
            try:
                self._write_population(enriched)
                self.record_event("EVOLUTION_POPULATION_UPDATED", {"alpha_id": alpha_id})
            except Exception:
                logging.info("Evolution population write skipped", exc_info=True)
            try:
                self._write_graph(enriched, reward, success)
                self.record_event("EVOLUTION_GRAPH_UPDATED", {"alpha_id": alpha_id})
            except Exception:
                logging.info("Evolution graph write skipped", exc_info=True)
            try:
                self._write_lineage_value(
                    {
                        "alpha_id": alpha_id,
                        "current_reward": reward,
                        "future_reward": finite_float(enriched.get("future_reward", 0.0), 0.0),
                        "long_term_value": finite_float(enriched.get("long_term_value", reward), reward),
                        "descendant_count": int(finite_float(enriched.get("descendant_count", 0), 0.0)),
                        "lookahead": int(getattr(self.config, "lineage_value_lookahead", 3) or 3),
                        "raw_payload": {"candidate": enriched, "success": success},
                    }
                )
                self.record_event("EVOLUTION_LINEAGE_VALUE_UPDATED", {"alpha_id": alpha_id})
            except Exception:
                logging.info("Evolution lineage value write skipped", exc_info=True)
            simulator_observation = candidate.get("simulator_observation") if isinstance(candidate.get("simulator_observation"), dict) else {}
            if simulator_observation:
                self._write_decision(
                    {
                        "generation": self._current_generation(),
                        "alpha_id": alpha_id,
                        "candidate_alpha_id": alpha_id,
                        "decision_type": "simulator_realized_result",
                        "action_type": "simulator",
                        "action_name": "realized_result",
                        "context_key": self.policy.context_key(context),
                        "simulator_score": simulator_observation.get("simulator_score", 0.0),
                        "reward": reward,
                        "success": success,
                        "raw_payload": {"simulator_observation": simulator_observation},
                    }
                )
            self._write_decision(
                {
                    "generation": self._current_generation(),
                    "alpha_id": alpha_id,
                    "candidate_alpha_id": alpha_id,
                    "decision_type": "reward_recorded",
                    "action_type": candidate_source or "unknown",
                    "action_name": mutation_type or "initial_or_untracked",
                    "context_key": self.policy.context_key(context),
                    "reward": reward,
                    "reward_delta": reward_delta,
                    "success": success,
                    "raw_payload": {
                        **evolution_authority(self.config, "reward_update", active_decision=True),
                        "candidate": enriched,
                        "reward_payload": reward_payload,
                    },
                }
            )
            protected_types = {"initial_or_untracked", "seed", "current_code", "unknown"}
            protected_sources = {"seed", "current_code", "initial_or_untracked", "legacy_parent", "template_initial"}
            is_pending = bool(enriched.get("is_pending_candidate", False))
            should_update_policy = (
                is_pending
                and bool(mutation_type)
                and mutation_type not in protected_types
                and candidate_source not in protected_sources
            )
            if should_update_policy:
                self._update_policy("mutation", mutation_type, reward_delta, success, context)
                if mutation_type == "crossover" or candidate_source == "crossover":
                    self._update_policy("evolution_mode", "crossover", reward_delta, success, context)
            else:
                self._write_decision(
                    {
                        "generation": self._current_generation(),
                        "alpha_id": alpha_id,
                        "candidate_alpha_id": alpha_id,
                        "decision_type": "policy_update_skipped",
                        "action_type": "policy",
                        "action_name": "skip_update",
                        "context_key": self.policy.context_key(context),
                        "reward": reward,
                        "reward_delta": reward_delta,
                        "success": success,
                        "skipped_reason": "non_pending_or_untracked_candidate",
                        "raw_payload": {
                            "is_pending_candidate": is_pending,
                            "mutation_type": mutation_type,
                            "candidate_source": candidate_source,
                        },
                    }
                )
            self.record_event("EVOLUTION_REWARD_RECORDED", {"alpha_id": alpha_id, "reward": reward, "reward_delta": reward_delta})
            self.record_event("EVOLUTION_SURVIVAL_SCORED", {"alpha_id": alpha_id, **overlay})
            return overlay
        except Exception:
            logging.info("Evolution after_backtest fallback", exc_info=True)
            self.record_event("EVOLUTION_FALLBACK_LEGACY_PATH", {"phase": "after_backtest"})
            return {}

    def _current_generation(self) -> int:
        try:
            return self.repo.get_current_generation() if self.repo is not None else 0
        except Exception:
            return 0

    def _write_decision(self, payload: dict[str, Any]) -> None:
        queued = False
        try:
            if self.storage is not None and hasattr(self.storage, "write_evolution_decision_record"):
                queued = bool(self.storage.write_evolution_decision_record(payload))
        except Exception:
            queued = False
            logging.info("Evolution decision queue write failed", exc_info=True)
        if queued:
            return
        try:
            if self.repo is not None:
                self.repo.record_decision(payload)
        except Exception:
            logging.info("Evolution decision repo write failed", exc_info=True)

    def _write_population(self, candidate: dict[str, Any]) -> None:
        if not isinstance(candidate, dict):
            return
        queued = False
        try:
            if self.storage is not None and hasattr(self.storage, "write_evolution_population_record"):
                queued = bool(self.storage.write_evolution_population_record(candidate))
        except Exception:
            queued = False
            logging.info("Evolution population queue write failed", exc_info=True)
        if queued:
            return
        try:
            if self.repo is not None:
                self.repo.upsert_population_member(candidate)
        except Exception:
            logging.info("Evolution population repo write failed", exc_info=True)

    def _write_policy(self, payload: dict[str, Any]) -> bool:
        queued = False
        try:
            if self.storage is not None and hasattr(self.storage, "write_evolution_policy_record"):
                queued = bool(self.storage.write_evolution_policy_record(payload))
        except Exception:
            queued = False
            logging.info("Evolution policy queue write failed", exc_info=True)
        if queued:
            return True
        try:
            if self.repo is not None:
                self.repo.upsert_policy_action(**payload)
                return True
        except Exception:
            logging.info("Evolution policy repo write failed", exc_info=True)
        return False

    def _update_policy(
        self,
        action_type: str,
        action_name: str,
        reward_delta: float,
        success: bool,
        context: dict[str, Any] | None = None,
    ) -> None:
        if not action_type or not action_name:
            return
        context = dict(context or {})
        payload = {
            "action_type": action_type,
            "action_name": action_name,
            "context_key": self.policy.context_key(context),
            "reward_delta": finite_float(reward_delta),
            "success": bool(success),
            "learning_rate": finite_float(getattr(self.config, "policy_learning_rate", 0.08), 0.08),
            "min_weight": finite_float(getattr(self.config, "policy_min_weight", 0.15), 0.15),
            "max_weight": finite_float(getattr(self.config, "policy_max_weight", 5.0), 5.0),
            "decay_rate": finite_float(getattr(self.config, "policy_decay_rate", 0.995), 0.995, minimum=0.0, maximum=1.0),
            "payload": {"context": context},
        }
        if not self._write_policy(payload):
            try:
                self.policy.update_after_result(action_type, action_name, reward_delta, success, context)
            except Exception:
                logging.info("Evolution policy update fallback failed", exc_info=True)
                return
        self._write_decision(
            {
                "generation": self._current_generation(),
                "decision_type": "policy_update",
                "action_type": action_type,
                "action_name": action_name,
                "context_key": payload["context_key"],
                "reward_delta": finite_float(reward_delta),
                "success": bool(success),
                "raw_payload": {
                    **evolution_authority(self.config, "policy", active_decision=True),
                    "context": context,
                },
            }
        )

    def _write_graph(self, candidate: dict[str, Any], reward: float, success: bool) -> None:
        queued_any = False
        for payload in self._graph_payloads(candidate, reward, success):
            queued = False
            try:
                if self.storage is not None and hasattr(self.storage, "write_evolution_graph_record"):
                    queued = bool(self.storage.write_evolution_graph_record(payload))
            except Exception:
                queued = False
                logging.info("Evolution graph queue write failed", exc_info=True)
            if queued:
                queued_any = True
                continue
            try:
                if self.repo is not None:
                    self.repo.upsert_graph_edge(
                        edge_type=str(payload.get("edge_type") or ""),
                        src=str(payload.get("src") or ""),
                        dst=str(payload.get("dst") or ""),
                        reward=finite_float(payload.get("reward", 0.0)),
                        success=bool(payload.get("success")),
                        payload=payload,
                    )
            except Exception:
                logging.info("Evolution graph repo write failed", exc_info=True)
        if not queued_any and self.repo is None:
            return

    def _graph_payloads(self, candidate: dict[str, Any], reward: float, success: bool) -> list[dict[str, Any]]:
        alpha_id = candidate.get("alpha_id")
        expression = str(candidate.get("expression") or candidate.get("code") or "")
        family = str(candidate.get("behavior_family") or candidate.get("family") or "unknown")
        mutation = str(candidate.get("mutation_type") or "unknown")
        rows: list[dict[str, Any]] = []
        try:
            operators = self.graph.extract_operators(expression) if self.graph else []
        except Exception:
            operators = []
        for left, right in zip(operators, operators[1:]):
            rows.append({"edge_type": "operator_pair", "src": left, "dst": right, "reward": reward, "success": success, "alpha_id": alpha_id})
        rows.append({"edge_type": "mutation_to_family", "src": mutation, "dst": family, "reward": reward, "success": success, "alpha_id": alpha_id})
        rows.append({"edge_type": "family_to_success", "src": family, "dst": "success" if success else "failure", "reward": reward, "success": success, "alpha_id": alpha_id})
        parent_ids = candidate.get("parent_ids") if isinstance(candidate.get("parent_ids"), list) else []
        for parent in parent_ids:
            if parent:
                rows.append({"edge_type": "parent_to_child", "src": str(parent), "dst": str(alpha_id or ""), "reward": reward, "success": success, "alpha_id": alpha_id})
        if mutation == "crossover" and len(parent_ids) >= 2:
            rows.append({"edge_type": "crossover_pair", "src": str(parent_ids[0]), "dst": str(parent_ids[1]), "reward": reward, "success": success, "child": alpha_id})
        failure_type = str(candidate.get("failure_type") or candidate.get("failure_reason") or "")
        if failure_type and mutation and mutation != "unknown":
            rows.append({"edge_type": "failure_to_repair", "src": failure_type[:120], "dst": mutation, "reward": reward, "success": success, "alpha_id": alpha_id})
        return rows

    def _write_lineage_value(self, payload: dict[str, Any]) -> None:
        queued = False
        try:
            if self.storage is not None and hasattr(self.storage, "write_lineage_value_record"):
                queued = bool(self.storage.write_lineage_value_record(payload))
        except Exception:
            queued = False
            logging.info("Evolution lineage queue write failed", exc_info=True)
        if queued:
            return
        try:
            if self.repo is not None:
                self.repo.upsert_lineage_value(str(payload.get("alpha_id") or ""), payload)
        except Exception:
            logging.info("Evolution lineage repo write failed", exc_info=True)

    def _write_simulator_observation(self, payload: dict[str, Any]) -> None:
        queued = False
        try:
            if self.storage is not None and hasattr(self.storage, "write_simulator_observation_record"):
                queued = bool(self.storage.write_simulator_observation_record(payload))
        except Exception:
            queued = False
            logging.info("Evolution simulator observation queue write failed", exc_info=True)
        if queued:
            return
        try:
            if self.repo is not None:
                self.repo.record_simulator_observation(payload)
        except Exception:
            logging.info("Evolution simulator observation repo write failed", exc_info=True)

    def record_storage_health(self) -> None:
        if self.repo is None:
            return
        try:
            stats = self.storage.stats() if hasattr(self.storage, "stats") else None
            payload = {
                "queue_size": getattr(stats, "backlog", 0),
                "db_path": str(getattr(self.storage, "db_path", "")),
                "last_import_completed": self.repo.get_meta("legacy_full_import_completed", ""),
                "population_size": self.repo.count_population(active_only=False),
                "policy_action_count": self.repo.count_policy_actions(),
                "graph_edge_count": self.repo.count_graph_edges(),
            }
            self.record_event("EVOLUTION_STORAGE_HEALTH", payload)
        except Exception:
            logging.info("Evolution storage health skipped", exc_info=True)

    def record_event(self, event_type: str, payload: dict[str, Any]) -> None:
        logging.info("%s %s", event_type, payload)
        if getattr(self.storage, "mode", "") == "jsonl_only":
            return
        try:
            self.storage.write_event(
                Path(EVOLUTION_EVENT_LOG_FILE),
                {"event": event_type, **(payload if isinstance(payload, dict) else {})},
                max_bytes=5 * 1024 * 1024,
            )
        except Exception:
            logging.info("Evolution event write skipped", exc_info=True)
