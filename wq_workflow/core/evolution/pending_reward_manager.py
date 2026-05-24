from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from ...paths import PENDING_REWARD_LOG_FILE, PENDING_REWARDS_FILE
from ...safe_io import append_jsonl, finite_float
from .survival_memory_manager import SurvivalMemoryManager
from .versioned_memory import VersionedEvolutionMemory


class PendingRewardManager:
    def __init__(
        self,
        path: Path = PENDING_REWARDS_FILE,
        log_path: Path = PENDING_REWARD_LOG_FILE,
        *,
        settle_after: int = 5,
        release_survival_rounds: int = 5,
        injection_weight: float = 0.15,
        max_injection_per_round: float = 1.0,
        injection_ema_alpha: float = 0.35,
        decay_halflife_generations: float = 12.0,
    ) -> None:
        self.path = path
        self.log_path = log_path
        self.settle_after = max(1, int(settle_after))
        self.release_survival_rounds = max(1, int(release_survival_rounds))
        self.injection_weight = max(0.0, finite_float(injection_weight))
        self.max_injection_per_round = max(0.0, finite_float(max_injection_per_round, 1.0))
        self.injection_ema_alpha = finite_float(injection_ema_alpha, 0.35, minimum=0.0, maximum=1.0)
        self.decay_halflife_generations = max(1.0, finite_float(decay_halflife_generations, 12.0))
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._store = VersionedEvolutionMemory(
            self.path,
            extra_defaults={"injections": self._empty_injections()},
        )

    def load_rewards(self) -> dict[str, dict[str, Any]]:
        payload = self._store.load_data()
        return {str(key): self._normalize_record(value) for key, value in payload.items() if isinstance(value, dict)}

    def load_injections(self) -> dict[str, Any]:
        injections = self._store.load_payload().get("injections", {})
        return self._normalize_injections(injections if isinstance(injections, dict) else {})

    def flush(self) -> None:
        self._store.flush()

    def close(self) -> None:
        self._store.close()

    def register_pending_reward(
        self,
        alpha_id: str,
        reward: float,
        *,
        created_generation: int = 0,
        settle_after: int | None = None,
        behavior_family: str = "",
        template: str = "",
        operator: str = "",
        lineage_depth: int = 0,
        lineage_root: str = "",
    ) -> dict[str, Any]:
        if not alpha_id:
            return {}
        reward = finite_float(reward)
        if reward <= 0:
            return {}
        rows = self.load_rewards()
        record = {
            "pending_reward": round(reward * 0.7, 6),
            "created_generation": max(0, int(created_generation or 0)),
            "settle_after": max(1, int(settle_after or self.settle_after)),
            "released": False,
            "canceled": False,
            "behavior_family": behavior_family or template or "legacy",
            "operator": operator or "unknown",
            "lineage_root": lineage_root or "",
            "lineage_depth": max(0, int(lineage_depth or 0)),
        }
        rows[alpha_id] = record
        self._save(rows)
        self._log("register_pending_reward", alpha_id, record)
        return dict(record)

    def settle_rewards(
        self,
        *,
        current_generation: int,
        survival_manager: SurvivalMemoryManager,
        current_behavior_family: str = "",
        current_template: str = "",
        current_operator: str = "",
        current_lineage: str = "",
    ) -> dict[str, Any]:
        rows = self.load_rewards()
        if not rows:
            return self._empty_settlement()
        memory = survival_manager.load_memory()
        injections = self.load_injections()
        released_total = 0.0
        canceled_total = 0.0
        released_count = 0
        canceled_count = 0
        changed = False
        generation = max(0, int(current_generation or 0))

        for alpha_id, record in rows.items():
            record = self._normalize_record(record)
            if record.get("released") or record.get("canceled"):
                continue
            created = max(0, int(record.get("created_generation") or 0))
            settle_after = max(1, int(record.get("settle_after") or self.settle_after))
            if generation - created < settle_after:
                continue
            survival_record = memory.get(alpha_id, {})
            pending_reward = finite_float(record.get("pending_reward"))
            if int(survival_record.get("survival_rounds") or 0) >= self.release_survival_rounds:
                self.release_reward(alpha_id, rows=rows, generation=generation)
                released_reward = pending_reward * self._settlement_factor(record, generation)
                released_total += released_reward
                released_count += 1
                injections = self._inject_reinforcement(injections, record, released_reward, generation)
            else:
                self.cancel_reward(alpha_id, rows=rows, generation=generation)
                canceled_total += pending_reward
                canceled_count += 1
            changed = True

        decay_before = repr(injections)
        injections = self._decay_injections(injections, generation)
        if repr(injections) != decay_before:
            changed = True
        if changed:
            self._save(rows, injections=injections)
        family = current_behavior_family or current_template
        direction_adjustment = self.compute_direction_adjustment(
            lineage=current_lineage,
            behavior_family=family,
            operator=current_operator,
        )
        result = {
            "released_total": round(released_total, 6),
            "canceled_total": round(canceled_total, 6),
            "released_count": released_count,
            "canceled_count": canceled_count,
            "adjustment": round(direction_adjustment, 6),
            "injection": self._direction_snapshot(
                injections,
                lineage=current_lineage,
                behavior_family=family,
                operator=current_operator,
            ),
        }
        if changed:
            self._log("settle_rewards", "", result)
        return result

    def cancel_reward(
        self,
        alpha_id: str,
        *,
        rows: dict[str, dict[str, Any]] | None = None,
        generation: int = 0,
    ) -> dict[str, Any]:
        owns_rows = rows is None
        rows = rows or self.load_rewards()
        record = rows.get(alpha_id)
        if not isinstance(record, dict):
            return {}
        record["canceled"] = True
        record["released"] = False
        record["settled_generation"] = max(0, int(generation or 0))
        if owns_rows:
            self._save(rows)
        self._log("cancel_reward", alpha_id, record)
        return dict(record)

    def release_reward(
        self,
        alpha_id: str,
        *,
        rows: dict[str, dict[str, Any]] | None = None,
        generation: int = 0,
    ) -> dict[str, Any]:
        owns_rows = rows is None
        rows = rows or self.load_rewards()
        record = rows.get(alpha_id)
        if not isinstance(record, dict):
            return {}
        record["released"] = True
        record["canceled"] = False
        record["settled_generation"] = max(0, int(generation or 0))
        if owns_rows:
            self._save(rows)
        self._log("release_reward", alpha_id, record)
        return dict(record)

    def immediate_reward(self, reward: float) -> float:
        reward = finite_float(reward)
        if reward <= 0:
            return reward
        return round(reward * 0.3, 6)

    def compute_direction_adjustment(
        self,
        *,
        lineage: str = "",
        behavior_family: str = "",
        operator: str = "",
    ) -> float:
        injections = self.load_injections()
        adjustment = finite_float(injections.get("global_reward_bias")) * 0.1
        if lineage:
            adjustment += finite_float(injections.get("lineage_score", {}).get(lineage)) * 0.4
        if behavior_family:
            adjustment += finite_float(injections.get("family_weight", {}).get(behavior_family)) * 0.3
        if operator:
            adjustment += finite_float(injections.get("operator_credibility", {}).get(operator)) * 0.2
        return round(adjustment * self.injection_weight, 6)

    def _inject_reinforcement(
        self,
        injections: dict[str, Any],
        record: dict[str, Any],
        released_reward: float,
        generation: int,
    ) -> dict[str, Any]:
        reward = max(0.0, finite_float(released_reward))
        if reward <= 0:
            return injections
        lineage = str(record.get("lineage_root") or record.get("parent") or "")
        family = str(record.get("behavior_family") or record.get("template") or "legacy")
        operator = str(record.get("operator") or "unknown")
        raw_parts = {
            "lineage_score": (lineage, reward * 0.4),
            "family_weight": (family, reward * 0.3),
            "operator_credibility": (operator, reward * 0.2),
        }
        remaining = self.max_injection_per_round
        for bucket, (key, amount) in raw_parts.items():
            if not key or remaining <= 0:
                continue
            applied = min(amount, remaining)
            remaining -= applied
            values = injections.setdefault(bucket, {})
            current = finite_float(values.get(key))
            values[key] = round(_ema(current, applied, self.injection_ema_alpha), 6)
        if remaining > 0:
            applied = min(reward * 0.1, remaining)
            current = finite_float(injections.get("global_reward_bias"))
            injections["global_reward_bias"] = round(_ema(current, applied, self.injection_ema_alpha), 6)
        injections["last_generation"] = max(0, int(generation or 0))
        return self._decay_injections(injections, generation)

    def _decay_injections(self, injections: dict[str, Any], generation: int) -> dict[str, Any]:
        previous = max(0, int(injections.get("last_decay_generation") or generation or 0))
        generation = max(0, int(generation or 0))
        if max(
            [abs(finite_float(injections.get("global_reward_bias")))]
            + [
                abs(finite_float(value))
                for bucket in ("lineage_score", "family_weight", "operator_credibility")
                for value in (injections.get(bucket, {}) if isinstance(injections.get(bucket), dict) else {}).values()
            ]
        ) <= 0:
            injections["last_decay_generation"] = generation
            return injections
        elapsed = max(0, generation - previous)
        if elapsed <= 0:
            injections["last_decay_generation"] = generation
            return injections
        decay = 0.5 ** (elapsed / self.decay_halflife_generations)
        for bucket in ("lineage_score", "family_weight", "operator_credibility"):
            values = injections.get(bucket)
            if isinstance(values, dict):
                for key in list(values):
                    decayed = finite_float(values.get(key)) * decay
                    if abs(decayed) < 1e-9:
                        values.pop(key, None)
                    else:
                        values[key] = round(decayed, 6)
        injections["global_reward_bias"] = round(finite_float(injections.get("global_reward_bias")) * decay, 6)
        injections["last_decay_generation"] = generation
        return injections

    def _settlement_factor(self, record: dict[str, Any], generation: int) -> float:
        created = max(0, int(record.get("created_generation") or 0))
        age = max(0, generation - created)
        return round(0.5 ** (age / self.decay_halflife_generations), 6)

    def _save(self, rows: dict[str, dict[str, Any]], *, injections: dict[str, Any] | None = None) -> None:
        meta = {"injections": self._normalize_injections(injections or self.load_injections())}
        cleaned = {str(key): self._normalize_record(value) for key, value in rows.items() if isinstance(value, dict)}
        self._store.save_data(cleaned, meta=meta)

    def _normalize_record(self, record: dict[str, Any]) -> dict[str, Any]:
        result = dict(record)
        result["pending_reward"] = finite_float(result.get("pending_reward"))
        result["created_generation"] = max(0, int(result.get("created_generation") or 0))
        result["settle_after"] = max(1, int(result.get("settle_after") or self.settle_after))
        result["released"] = bool(result.get("released"))
        result["canceled"] = bool(result.get("canceled"))
        result["behavior_family"] = str(result.get("behavior_family") or result.get("template") or "legacy")
        result["operator"] = str(result.get("operator") or "unknown")
        result["lineage_root"] = str(result.get("lineage_root") or result.get("parent") or "")
        result["lineage_depth"] = max(0, int(result.get("lineage_depth") or 0))
        if "settled_generation" in result:
            result["settled_generation"] = max(0, int(result.get("settled_generation") or 0))
        return result

    def _empty_injections(self) -> dict[str, Any]:
        return {
            "lineage_score": {},
            "family_weight": {},
            "operator_credibility": {},
            "global_reward_bias": 0.0,
            "last_generation": 0,
            "last_decay_generation": 0,
        }

    def _normalize_injections(self, injections: dict[str, Any]) -> dict[str, Any]:
        normalized = self._empty_injections()
        for bucket in ("lineage_score", "family_weight", "operator_credibility"):
            values = injections.get(bucket)
            if isinstance(values, dict):
                normalized[bucket] = {str(key): finite_float(value) for key, value in values.items()}
        normalized["global_reward_bias"] = finite_float(injections.get("global_reward_bias"))
        normalized["last_generation"] = max(0, int(injections.get("last_generation") or 0))
        normalized["last_decay_generation"] = max(0, int(injections.get("last_decay_generation") or 0))
        return normalized

    def _direction_snapshot(
        self,
        injections: dict[str, Any],
        *,
        lineage: str,
        behavior_family: str,
        operator: str,
    ) -> dict[str, Any]:
        return {
            "lineage_score": finite_float(injections.get("lineage_score", {}).get(lineage)) if lineage else 0.0,
            "family_weight": finite_float(injections.get("family_weight", {}).get(behavior_family)) if behavior_family else 0.0,
            "operator_credibility": finite_float(injections.get("operator_credibility", {}).get(operator)) if operator else 0.0,
            "global_reward_bias": finite_float(injections.get("global_reward_bias")),
        }

    def _log(self, event: str, alpha_id: str, payload: dict[str, Any]) -> None:
        append_jsonl(
            self.log_path,
            {
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "event": event,
                "alpha_id": alpha_id,
                **payload,
            },
        )

    def _empty_settlement(self) -> dict[str, Any]:
        return {
            "released_total": 0.0,
            "canceled_total": 0.0,
            "released_count": 0,
            "canceled_count": 0,
            "adjustment": 0.0,
            "injection": self._direction_snapshot(self.load_injections(), lineage="", behavior_family="", operator=""),
        }


def _ema(current: float, incoming: float, alpha: float) -> float:
    return current * (1.0 - alpha) + incoming * alpha
