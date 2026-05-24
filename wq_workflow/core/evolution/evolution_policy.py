from __future__ import annotations

import random
from typing import Any

from ...mutation_engine import MUTATION_OPERATORS
from ...safe_io import finite_float
from .authority import evolution_authority


def suggest_mutation_weights(history: Any) -> dict[str, float]:
    rows = _history_rows(history)
    weights = {name: 1.0 for name in MUTATION_OPERATORS}
    if not rows:
        return weights

    grouped: dict[str, dict[str, float]] = {}
    for row in rows:
        mutation = str(row.get("mutation_type") or row.get("operator") or "")
        if mutation not in weights:
            continue
        bucket = grouped.setdefault(mutation, {"count": 0.0, "reward_sum": 0.0, "success_count": 0.0})
        reward = finite_float(row.get("reward"))
        bucket["count"] += 1.0
        bucket["reward_sum"] += reward
        if reward > 0 or row.get("passed") or row.get("quality_passed"):
            bucket["success_count"] += 1.0

    for mutation, stats in grouped.items():
        count = max(1.0, stats.get("count", 0.0))
        avg_reward = stats.get("reward_sum", 0.0) / count
        success_rate = stats.get("success_count", 0.0) / count
        weights[mutation] = round(max(0.05, 1.0 + avg_reward + success_rate * 0.5), 6)
    return weights


class EvolutionPolicy:
    def __init__(self, repository: Any | None = None, config: Any | None = None) -> None:
        self.repository = repository
        self.config = config

    def suggest_mutation_weights(self, history: Any) -> dict[str, float]:
        return suggest_mutation_weights(history)

    def context_key(self, context: dict[str, Any] | None = None) -> str:
        context = context or {}
        parts = []
        mapping = {
            "failure": context.get("failure_type") or context.get("failure_reason") or context.get("mutation_goal"),
            "family": context.get("behavior_family") or context.get("family"),
            "goal": context.get("mutation_goal"),
            "turnover": _bucket(context.get("turnover") or _metric(context.get("current_metrics"), "turnover"), [20, 50, 70]),
            "corr": _bucket(context.get("estimated_self_corr"), [0.35, 0.7, 0.9]),
            "complexity": _complexity_bucket(context.get("complexity")),
        }
        for key, value in mapping.items():
            text = str(value or "").strip().lower()
            if text:
                parts.append(f"{key}={text[:40]}")
        return "|".join(parts) or "global"

    def clamp(self, value: float) -> float:
        return max(
            float(getattr(self.config, "policy_min_weight", 0.15) or 0.15),
            min(float(getattr(self.config, "policy_max_weight", 5.0) or 5.0), finite_float(value, 1.0)),
        )

    def get_config_prior(self, action_type: str, action_name: str) -> float:
        if action_type == "evolution_mode":
            if action_name == "crossover":
                return finite_float(getattr(self.config, "crossover_rate", 0.25), 0.25, minimum=0.0)
            if action_name == "mutation":
                return finite_float(getattr(self.config, "mutation_rate", 0.70), 0.70, minimum=0.0)
            if action_name == "random_seed":
                return finite_float(getattr(self.config, "random_seed_rate", 0.05), 0.05, minimum=0.0)
        if action_type == "crossover":
            if action_name == "crossover":
                return finite_float(getattr(self.config, "crossover_rate", 0.25), 0.25, minimum=0.0)
            if action_name == "mutation":
                return finite_float(getattr(self.config, "mutation_rate", 0.70), 0.70, minimum=0.0)
        return 1.0

    def apply_context_adjustment(self, action_type: str, action_name: str, base: float, context: dict[str, Any]) -> float:
        name = str(action_name)
        failure = str(context.get("failure_type") or context.get("mutation_goal") or context.get("failure_reason") or "").lower()
        adjusted = finite_float(base, 1.0, minimum=0.0)
        if "turnover" in failure and name in {"add_decay", "hump", "reduce_turnover"}:
            adjusted *= 1.25
        if "fitness" in failure and name in {"neutralize", "rank", "winsorize", "add_neutralization", "add_rank"}:
            adjusted *= 1.15
        if ("correlation" in failure or "corr" in failure) and name in {"replace_signal", "regime_shift", "cross_family"}:
            adjusted *= 1.20
        if action_type == "evolution_mode" and name == "crossover" and context.get("force_diversity"):
            adjusted *= 1.10
        return adjusted

    def normalize_weights(self, weights: dict[str, float]) -> dict[str, float]:
        total = sum(max(0.0, finite_float(value, 0.0)) for value in weights.values())
        if total <= 0:
            return {key: 1.0 / max(1, len(weights)) for key in weights}
        return {key: max(0.0, finite_float(value, 0.0)) / total for key, value in weights.items()}

    def get_action_weights(self, action_type: str, allowed_actions: list[str], context: dict[str, Any] | None = None) -> dict[str, float]:
        context = context or {}
        context_key = self.context_key(context)
        db_weights: dict[str, float] = {}
        if self.repository is not None:
            try:
                db_weights.update(self.repository.get_policy_weights(action_type, "global"))
                db_weights.update(self.repository.get_policy_weights(action_type, context_key))
            except Exception:
                db_weights = {}
        weights: dict[str, float] = {}
        for action in allowed_actions or []:
            name = str(action)
            prior = self.get_config_prior(action_type, name)
            learned = finite_float(db_weights.get(name, 1.0), 1.0, minimum=0.01)
            base = self.apply_context_adjustment(action_type, name, prior * learned, context)
            if action_type == "evolution_mode":
                weights[name] = max(0.0, min(finite_float(getattr(self.config, "policy_max_weight", 5.0), 5.0), finite_float(base, 0.0)))
            else:
                weights[name] = self.clamp(base)
        return self.normalize_weights(weights)

    def select_action(self, action_type: str, allowed_actions: list[str], context: dict[str, Any] | None = None) -> tuple[str | None, dict[str, float]]:
        weights = self.get_action_weights(action_type, allowed_actions, context)
        if not weights:
            return None, {}
        epsilon = finite_float(getattr(self.config, "policy_epsilon_explore", 0.12), 0.12, minimum=0.0, maximum=1.0)
        if random.random() < epsilon:
            return random.choice(list(weights.keys())), weights
        total = sum(max(0.0, float(value)) for value in weights.values())
        draw = random.random() * max(total, 0.01)
        running = 0.0
        for action, weight in weights.items():
            running += max(0.0, float(weight))
            if running >= draw:
                return action, weights
        return next(iter(weights)), weights

    def update_after_result(
        self,
        action_type: str,
        action_name: str,
        reward_delta: float,
        success: bool,
        context: dict[str, Any] | None = None,
    ) -> None:
        if self.repository is None or not action_type or not action_name:
            return
        stats = self.repository.upsert_policy_action(
            action_type=action_type,
            action_name=action_name,
            context_key=self.context_key(context or {}),
            reward_delta=finite_float(reward_delta),
            success=bool(success),
            learning_rate=finite_float(getattr(self.config, "policy_learning_rate", 0.08), 0.08),
            min_weight=finite_float(getattr(self.config, "policy_min_weight", 0.15), 0.15),
            max_weight=finite_float(getattr(self.config, "policy_max_weight", 5.0), 5.0),
            decay_rate=finite_float(getattr(self.config, "policy_decay_rate", 0.995), 0.995, minimum=0.0, maximum=1.0),
            payload={"context": context or {}},
        )
        try:
            self.repository.record_decision(
                {
                    "generation": self.repository.get_current_generation(),
                    "decision_type": "policy_update",
                    "action_type": action_type,
                    "action_name": action_name,
                    "context_key": self.context_key(context or {}),
                    "reward_delta": finite_float(reward_delta),
                    "success": bool(success),
                    "raw_payload": {
                        **evolution_authority(self.config, "policy", active_decision=True),
                        "stats": stats,
                        "context": context or {},
                    },
                }
            )
        except Exception:
            pass


def _history_rows(history: Any) -> list[dict[str, Any]]:
    if isinstance(history, list):
        return [row for row in history if isinstance(row, dict)]
    if isinstance(history, dict):
        rows = history.get("history")
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
        stats = history.get("mutation_stats")
        if isinstance(stats, dict):
            result: list[dict[str, Any]] = []
            for mutation, values in stats.items():
                if not isinstance(values, dict):
                    continue
                count = int(finite_float(values.get("count"), 1.0, minimum=1.0))
                reward = finite_float(values.get("avg_reward_delta") or values.get("avg_reward"))
                success_rate = finite_float(values.get("success_rate"), minimum=0.0, maximum=1.0)
                result.append(
                    {
                        "mutation_type": str(mutation),
                        "reward": reward,
                        "passed": success_rate > 0,
                        "count": count,
                    }
                )
            return result
    return []


def _metric(metrics: Any, key: str) -> float:
    return finite_float(metrics.get(key) if isinstance(metrics, dict) else None)


def _bucket(value: Any, thresholds: list[float]) -> str:
    number = finite_float(value, 0.0)
    labels = ["low", "medium", "high", "extreme"]
    for index, threshold in enumerate(thresholds):
        if number <= threshold:
            return labels[index]
    return labels[-1]


def _complexity_bucket(value: Any) -> str:
    if isinstance(value, dict):
        value = value.get("operator_count") or value.get("current_operator_count") or 0
    number = finite_float(value, 0.0)
    if number <= 8:
        return "low"
    if number <= 18:
        return "medium"
    if number <= 32:
        return "high"
    return "extreme"
