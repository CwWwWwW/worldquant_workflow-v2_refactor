from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from datetime import datetime
from typing import Any


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _clean(value: Any) -> Any:
    if isinstance(value, float):
        return value if math.isfinite(value) else 0.0
    if isinstance(value, dict):
        return {str(key): _clean(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(item) for item in value]
    return value


def _json(value: Any) -> str:
    return json.dumps(_clean(value), ensure_ascii=False, allow_nan=False, default=str)


def _payload(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _loads_list(raw: str | None) -> list[Any]:
    try:
        value = json.loads(raw or "[]")
    except (TypeError, json.JSONDecodeError):
        return []
    return value if isinstance(value, list) else []


def _float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(number):
        return default
    return number


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _fingerprint(expression: str) -> str:
    normalized = "".join((expression or "").lower().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:20]


class EvolutionDBRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def upsert_population_member(self, payload: dict[str, Any]) -> None:
        alpha_id = str(payload.get("alpha_id") or payload.get("alpha_name") or "")
        expression = str(payload.get("expression") or payload.get("code") or payload.get("expression_after") or "")
        if not alpha_id or not expression:
            return
        family = str(payload.get("family") or payload.get("behavior_family") or "unknown")
        metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
        complexity = payload.get("complexity") if isinstance(payload.get("complexity"), dict) else {}
        self.conn.execute(
            """
            INSERT INTO evolution_population
            (alpha_id, expression, generation, family, reward, survival_score, long_term_value,
             lineage_depth, parent_ids, mutation_history, metrics, complexity, status,
             birth_source, created_at, updated_at, raw_payload)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(alpha_id) DO UPDATE SET
              expression = excluded.expression,
              generation = excluded.generation,
              family = excluded.family,
              reward = excluded.reward,
              survival_score = excluded.survival_score,
              long_term_value = excluded.long_term_value,
              lineage_depth = excluded.lineage_depth,
              parent_ids = excluded.parent_ids,
              mutation_history = excluded.mutation_history,
              metrics = excluded.metrics,
              complexity = excluded.complexity,
              status = excluded.status,
              updated_at = excluded.updated_at,
              raw_payload = excluded.raw_payload
            """,
            (
                alpha_id,
                expression,
                _int(payload.get("generation", 0)),
                family,
                _float(payload.get("reward", payload.get("score", 0.0))),
                _float(payload.get("survival_score", 0.0)),
                _float(payload.get("long_term_value", 0.0)),
                _int(payload.get("lineage_depth", 0)),
                _json(payload.get("parent_ids") or []),
                _json(payload.get("mutation_history") or []),
                _json(metrics),
                _json(complexity),
                str(payload.get("status") or "active"),
                str(payload.get("birth_source") or payload.get("source") or "unknown"),
                str(payload.get("created_at") or payload.get("timestamp") or _now()),
                _now(),
                _json(payload),
            ),
        )

    def list_population(self, limit: int = 80, active_only: bool = True) -> list[dict[str, Any]]:
        params: list[Any] = []
        sql = "SELECT * FROM evolution_population"
        if active_only:
            sql += " WHERE status = ?"
            params.append("active")
        sql += " ORDER BY survival_score DESC, long_term_value DESC, reward DESC LIMIT ?"
        params.append(max(1, int(limit)))
        rows = self.conn.execute(sql, tuple(params)).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            payload = _payload(row["raw_payload"])
            payload.update(
                {
                    "alpha_id": row["alpha_id"],
                    "expression": row["expression"],
                    "generation": row["generation"],
                    "family": row["family"],
                    "behavior_family": payload.get("behavior_family", row["family"]),
                    "reward": row["reward"],
                    "survival_score": row["survival_score"],
                    "long_term_value": row["long_term_value"],
                    "lineage_depth": row["lineage_depth"],
                    "status": row["status"],
                    "birth_source": row["birth_source"],
                }
            )
            payload.setdefault("parent_ids", _loads_list(row["parent_ids"]))
            payload.setdefault("mutation_history", _loads_list(row["mutation_history"]))
            payload.setdefault("metrics", _payload(row["metrics"]))
            payload.setdefault("complexity", _payload(row["complexity"]))
            result.append(payload)
        return result

    def mark_population_status(self, alpha_id: str, status: str) -> None:
        if not alpha_id:
            return
        self.conn.execute(
            "UPDATE evolution_population SET status = ?, updated_at = ? WHERE alpha_id = ?",
            (str(status or "archived"), _now(), alpha_id),
        )

    def insert_generation_summary(self, payload: dict[str, Any]) -> None:
        generation = _int(payload.get("generation", self.get_current_generation()))
        self.conn.execute(
            """
            INSERT INTO evolution_generations
            (generation, population_size, best_alpha_id, best_reward, avg_reward,
             avg_survival_score, family_entropy, diversity_score, created_at, raw_payload)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(generation) DO UPDATE SET
              population_size = excluded.population_size,
              best_alpha_id = excluded.best_alpha_id,
              best_reward = excluded.best_reward,
              avg_reward = excluded.avg_reward,
              avg_survival_score = excluded.avg_survival_score,
              family_entropy = excluded.family_entropy,
              diversity_score = excluded.diversity_score,
              raw_payload = excluded.raw_payload
            """,
            (
                generation,
                _int(payload.get("population_size", 0)),
                str(payload.get("best_alpha_id") or ""),
                _float(payload.get("best_reward", 0.0)),
                _float(payload.get("avg_reward", 0.0)),
                _float(payload.get("avg_survival_score", 0.0)),
                _float(payload.get("family_entropy", 0.0)),
                _float(payload.get("diversity_score", 0.0)),
                str(payload.get("created_at") or _now()),
                _json(payload),
            ),
        )
        self.conn.execute(
            """
            INSERT INTO evolution_meta (meta_key, meta_value, updated_at)
            VALUES ('current_generation', ?, ?)
            ON CONFLICT(meta_key) DO UPDATE SET meta_value = excluded.meta_value, updated_at = excluded.updated_at
            """,
            (str(generation), _now()),
        )

    def get_current_generation(self) -> int:
        row = self.conn.execute("SELECT meta_value FROM evolution_meta WHERE meta_key = 'current_generation'").fetchone()
        if row is not None:
            return _int(row["meta_value"], 0)
        row = self.conn.execute("SELECT MAX(generation) AS generation FROM evolution_generations").fetchone()
        return _int(row["generation"] if row is not None else 0, 0)

    def get_meta(self, key: str, default: Any = None) -> Any:
        if not key:
            return default
        row = self.conn.execute("SELECT meta_value FROM evolution_meta WHERE meta_key = ?", (str(key),)).fetchone()
        return row["meta_value"] if row is not None else default

    def set_meta(self, key: str, value: Any) -> None:
        if not key:
            return
        self.conn.execute(
            """
            INSERT INTO evolution_meta (meta_key, meta_value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(meta_key) DO UPDATE SET meta_value = excluded.meta_value, updated_at = excluded.updated_at
            """,
            (str(key), str(value), _now()),
        )

    def count_population(self, active_only: bool = True) -> int:
        if active_only:
            row = self.conn.execute("SELECT COUNT(*) AS count FROM evolution_population WHERE status = 'active'").fetchone()
        else:
            row = self.conn.execute("SELECT COUNT(*) AS count FROM evolution_population").fetchone()
        return _int(row["count"] if row is not None else 0, 0)

    def count_policy_actions(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) AS count FROM evolution_policy_actions").fetchone()
        return _int(row["count"] if row is not None else 0, 0)

    def count_graph_edges(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) AS count FROM alpha_graph_edges").fetchone()
        return _int(row["count"] if row is not None else 0, 0)

    def record_decision(self, payload: dict[str, Any]) -> None:
        self.conn.execute(
            """
            INSERT INTO evolution_decisions
            (generation, alpha_id, candidate_alpha_id, decision_type, parent_a, parent_b,
             action_type, action_name, context_key, weights, selected_weight,
             simulator_score, skipped, skipped_reason, reward, reward_delta,
             success, created_at, raw_payload)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _int(payload.get("generation", 0)),
                str(payload.get("alpha_id") or ""),
                str(payload.get("candidate_alpha_id") or ""),
                str(payload.get("decision_type") or ""),
                str(payload.get("parent_a") or ""),
                str(payload.get("parent_b") or ""),
                str(payload.get("action_type") or ""),
                str(payload.get("action_name") or ""),
                str(payload.get("context_key") or "global"),
                _json(payload.get("weights") or {}),
                _float(payload.get("selected_weight", 0.0)),
                _float(payload.get("simulator_score", 0.0)),
                1 if payload.get("skipped") else 0,
                str(payload.get("skipped_reason") or ""),
                _float(payload.get("reward", 0.0)),
                _float(payload.get("reward_delta", 0.0)),
                1 if payload.get("success") else 0,
                str(payload.get("created_at") or _now()),
                _json(payload),
            ),
        )

    def upsert_policy_action(
        self,
        *,
        action_type: str,
        action_name: str,
        context_key: str = "global",
        reward_delta: float = 0.0,
        success: bool = False,
        learning_rate: float = 0.08,
        min_weight: float = 0.15,
        max_weight: float = 5.0,
        decay_rate: float = 0.995,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not action_type or not action_name:
            return {}
        row = self.conn.execute(
            """
            SELECT * FROM evolution_policy_actions
            WHERE action_type = ? AND action_name = ? AND context_key = ?
            """,
            (action_type, action_name, context_key or "global"),
        ).fetchone()
        if row:
            count = _int(row["count"], 0) + 1
            reward_sum = _float(row["reward_sum"], 0.0) + _float(reward_delta, 0.0)
            success_count = _int(row["success_count"], 0) + (1 if success else 0)
            old_weight = _float(row["weight"], 1.0)
        else:
            count = 1
            reward_sum = _float(reward_delta, 0.0)
            success_count = 1 if success else 0
            old_weight = 1.0
        old_weight_before_decay = old_weight
        decay = max(0.0, min(1.0, _float(decay_rate, 0.995)))
        old_weight = 1.0 + (old_weight - 1.0) * decay
        avg_reward = reward_sum / max(1, count)
        success_rate = success_count / max(1, count)
        target_weight = 1.0 + avg_reward + 0.5 * success_rate
        lr = max(0.0, min(1.0, _float(learning_rate, 0.08)))
        new_weight = old_weight * (1.0 - lr) + target_weight * lr
        new_weight = max(_float(min_weight, 0.15), min(_float(max_weight, 5.0), new_weight))
        self.conn.execute(
            """
            INSERT INTO evolution_policy_actions
            (action_type, action_name, context_key, count, reward_sum, avg_reward,
             success_count, success_rate, weight, updated_at, raw_payload)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(action_type, action_name, context_key) DO UPDATE SET
              count = excluded.count,
              reward_sum = excluded.reward_sum,
              avg_reward = excluded.avg_reward,
              success_count = excluded.success_count,
              success_rate = excluded.success_rate,
              weight = excluded.weight,
              updated_at = excluded.updated_at,
              raw_payload = excluded.raw_payload
            """,
            (
                action_type,
                action_name,
                context_key or "global",
                count,
                reward_sum,
                avg_reward,
                success_count,
                success_rate,
                new_weight,
                _now(),
                _json(payload or {}),
            ),
        )
        return {
            "old_weight": old_weight_before_decay,
            "decayed_weight": old_weight,
            "new_weight": new_weight,
            "count": count,
            "avg_reward": avg_reward,
            "success_rate": success_rate,
        }

    def get_policy_weights(self, action_type: str, context_key: str = "global") -> dict[str, float]:
        rows = self.conn.execute(
            """
            SELECT action_name, weight, context_key FROM evolution_policy_actions
            WHERE action_type = ? AND context_key IN (?, 'global')
            ORDER BY CASE WHEN context_key = ? THEN 0 ELSE 1 END
            """,
            (action_type, context_key or "global", context_key or "global"),
        ).fetchall()
        weights: dict[str, float] = {}
        for row in rows:
            name = str(row["action_name"])
            if name not in weights:
                weights[name] = max(0.01, _float(row["weight"], 1.0))
        return weights

    def upsert_graph_edge(self, edge_type: str, src: str, dst: str, reward: float = 0.0, success: bool = False, payload: dict[str, Any] | None = None) -> None:
        if not edge_type or not src or not dst:
            return
        row = self.conn.execute(
            "SELECT * FROM alpha_graph_edges WHERE edge_type = ? AND src = ? AND dst = ?",
            (edge_type, src, dst),
        ).fetchone()
        if row:
            count = _int(row["count"], 0) + 1
            reward_sum = _float(row["reward_sum"], 0.0) + _float(reward, 0.0)
            success_count = _int(row["success_count"], 0) + (1 if success else 0)
        else:
            count = 1
            reward_sum = _float(reward, 0.0)
            success_count = 1 if success else 0
        avg_reward = reward_sum / max(1, count)
        success_rate = success_count / max(1, count)
        self.conn.execute(
            """
            INSERT INTO alpha_graph_edges
            (edge_type, src, dst, count, reward_sum, avg_reward, success_count, success_rate, updated_at, raw_payload)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(edge_type, src, dst) DO UPDATE SET
              count = excluded.count,
              reward_sum = excluded.reward_sum,
              avg_reward = excluded.avg_reward,
              success_count = excluded.success_count,
              success_rate = excluded.success_rate,
              updated_at = excluded.updated_at,
              raw_payload = excluded.raw_payload
            """,
            (edge_type, src, dst, count, reward_sum, avg_reward, success_count, success_rate, _now(), _json(payload or {})),
        )

    def list_graph_edges(self, edge_type: str, limit: int = 100) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT * FROM alpha_graph_edges
            WHERE edge_type = ?
            ORDER BY avg_reward DESC, success_rate DESC, count DESC
            LIMIT ?
            """,
            (edge_type, max(1, int(limit))),
        ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            payload = _payload(row["raw_payload"])
            payload.update(dict(row))
            result.append(payload)
        return result

    def upsert_lineage_value(self, alpha_id: str, payload: dict[str, Any]) -> None:
        if not alpha_id:
            return
        self.conn.execute(
            """
            INSERT INTO lineage_values
            (alpha_id, current_reward, future_reward, long_term_value, descendant_count, lookahead, updated_at, raw_payload)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(alpha_id) DO UPDATE SET
              current_reward = excluded.current_reward,
              future_reward = excluded.future_reward,
              long_term_value = excluded.long_term_value,
              descendant_count = excluded.descendant_count,
              lookahead = excluded.lookahead,
              updated_at = excluded.updated_at,
              raw_payload = excluded.raw_payload
            """,
            (
                alpha_id,
                _float(payload.get("current_reward", 0.0)),
                _float(payload.get("future_reward", 0.0)),
                _float(payload.get("long_term_value", 0.0)),
                _int(payload.get("descendant_count", 0)),
                _int(payload.get("lookahead", 3)),
                _now(),
                _json(payload),
            ),
        )
        self.conn.execute(
            "UPDATE evolution_population SET long_term_value = ?, updated_at = ? WHERE alpha_id = ?",
            (_float(payload.get("long_term_value", 0.0)), _now(), alpha_id),
        )

    def record_simulator_observation(self, payload: dict[str, Any]) -> None:
        self.conn.execute(
            """
            INSERT INTO simulator_observations
            (alpha_id, expression, simulator_score, flags, skipped, skipped_reason, parent_reward, created_at, raw_payload)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(payload.get("alpha_id") or payload.get("alpha_name") or ""),
                str(payload.get("expression") or payload.get("code") or ""),
                _float(payload.get("simulator_score", 0.0)),
                _json(payload.get("flags") or []),
                1 if payload.get("skipped") else 0,
                str(payload.get("skipped_reason") or ""),
                _float(payload.get("parent_reward", 0.0)),
                str(payload.get("created_at") or _now()),
                _json(payload),
            ),
        )

    def bootstrap_population_from_legacy(self, limit: int = 2000) -> int:
        rows: list[dict[str, Any]] = []
        for row in self.conn.execute("SELECT raw_payload, alpha_id, expression, reward, score FROM candidate_pool LIMIT ?", (max(1, int(limit)),)).fetchall():
            payload = _payload(row["raw_payload"])
            payload.setdefault("alpha_id", row["alpha_id"])
            payload.setdefault("expression", row["expression"])
            payload.setdefault("reward", row["reward"] if row["reward"] is not None else row["score"])
            payload.setdefault("birth_source", "legacy_candidate_pool")
            rows.append(payload)
        for row in self.conn.execute("SELECT raw_payload, alpha_id, expression, score FROM alpha_runs ORDER BY id DESC LIMIT ?", (max(1, int(limit)),)).fetchall():
            payload = _payload(row["raw_payload"])
            payload.setdefault("alpha_id", row["alpha_id"])
            payload.setdefault("expression", row["expression"])
            payload.setdefault("reward", row["score"])
            payload.setdefault("birth_source", "legacy_alpha_runs")
            rows.append(payload)

        seen: dict[str, dict[str, Any]] = {}
        generated = 0
        for row in rows:
            expression = str(row.get("expression") or row.get("code") or row.get("expression_after") or "")
            if not expression:
                continue
            key = _fingerprint(expression)
            if not row.get("alpha_id"):
                generated += 1
                row["alpha_id"] = f"legacy_bootstrap_{generated}_{key[:8]}"
            row.setdefault("status", "active")
            row.setdefault("birth_source", "legacy_bootstrap")
            if "survival_score" not in row:
                row["survival_score"] = max(0.0, min(1.0, (_float(row.get("reward", row.get("score", 0.0))) + 10.0) / 20.0))
            previous = seen.get(key)
            if previous is None or _float(row.get("reward", row.get("score", 0.0))) > _float(previous.get("reward", previous.get("score", 0.0))):
                seen[key] = row
        for row in seen.values():
            self.upsert_population_member(row)
        return len(seen)
