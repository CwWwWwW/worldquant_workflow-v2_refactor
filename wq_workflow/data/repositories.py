from __future__ import annotations

import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from .json_utils import json_dumps_safe, json_loads_safe, safe_float, safe_int
from .migrations import initialize_refactor_tables


def _now() -> str:
    return datetime.now().isoformat(timespec="microseconds")


def _new_id(prefix: str) -> str:
    return f"{prefix}:{uuid.uuid4().hex}"


def _db_path_from(storage: Any | None, db_path: str | Path | None) -> Path | None:
    if db_path is not None:
        return Path(db_path)
    return getattr(getattr(storage, "config", None), "db_path", None)


class BaseRepository:
    def __init__(self, conn: sqlite3.Connection | None = None, *, storage: Any | None = None, db_path: str | Path | None = None) -> None:
        self.conn = conn
        self.storage = storage
        path = _db_path_from(storage, db_path)
        self.db_path = Path(path) if path is not None else None

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        if self.conn is not None:
            self.conn.row_factory = sqlite3.Row
            initialize_refactor_tables(self.conn)
            yield self.conn
            return
        if self.db_path is None:
            raise RuntimeError("database path unavailable")
        from wq_workflow.storage.schema import initialize_schema
        from wq_workflow.storage.sqlite_store import connect_db

        conn = connect_db(self.db_path)
        try:
            initialize_schema(conn)
            yield conn
        finally:
            conn.close()

    def _commit(self, conn: sqlite3.Connection) -> None:
        try:
            conn.commit()
        except Exception:
            pass


class CandidateRepository(BaseRepository):
    def upsert_candidate(self, candidate: dict[str, Any]) -> None:
        data = candidate if isinstance(candidate, dict) else {}
        alpha_id = str(data.get("alpha_id") or data.get("alpha_name") or "")
        if not alpha_id:
            return
        metrics = data.get("metrics") if isinstance(data.get("metrics"), dict) else {}
        reward = safe_float(data.get("reward", data.get("score")), 0.0)
        updated_at = str(data.get("updated_at") or data.get("timestamp") or data.get("created_at") or _now())
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO candidate_pool (alpha_id, expression, reward, score, passed, created_at, updated_at, raw_payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(alpha_id) DO UPDATE SET
                  expression = excluded.expression,
                  reward = excluded.reward,
                  score = excluded.score,
                  passed = excluded.passed,
                  updated_at = excluded.updated_at,
                  raw_payload = excluded.raw_payload
                """,
                (
                    alpha_id,
                    str(data.get("expression") or data.get("code") or ""),
                    reward,
                    safe_float(data.get("score"), reward),
                    1 if data.get("passed") or data.get("template_success") or data.get("success") else 0,
                    str(data.get("created_at") or data.get("timestamp") or _now()),
                    updated_at,
                    json_dumps_safe(data),
                ),
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO alpha_runs
                (alpha_id, expression, fitness, sharpe, turnover, margin, score, result, created_at, raw_payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    alpha_id,
                    str(data.get("expression") or data.get("code") or ""),
                    safe_float(data.get("fitness", metrics.get("fitness")), 0.0),
                    safe_float(data.get("sharpe", metrics.get("sharpe")), 0.0),
                    safe_float(data.get("turnover", metrics.get("turnover")), 0.0),
                    safe_float(data.get("margin", metrics.get("margin")), 0.0),
                    reward,
                    str(data.get("result") or ("passed" if data.get("passed") or data.get("success") else "")),
                    str(data.get("created_at") or data.get("timestamp") or _now()),
                    json_dumps_safe(data),
                ),
            )
            self._commit(conn)

    def get_candidate(self, alpha_id: str) -> dict[str, Any] | None:
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM candidate_pool WHERE alpha_id=?", (alpha_id,)).fetchone()
            if row is None:
                return None
            payload = json_loads_safe(row["raw_payload"] if hasattr(row, "keys") else row[7], {})
            result = dict(payload) if isinstance(payload, dict) else {}
            keys = row.keys() if hasattr(row, "keys") else ["alpha_id", "expression", "reward", "score", "passed", "created_at", "updated_at", "raw_payload"]
            row_dict = {key: row[key] for key in keys}
            result.update({k: v for k, v in row_dict.items() if k != "raw_payload"})
            return result

    def list_recent_candidates(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute("SELECT raw_payload FROM candidate_pool ORDER BY updated_at DESC LIMIT ?", (max(1, int(limit)),)).fetchall()
            return [json_loads_safe(row[0], {}) for row in rows]


class IterationRepository(BaseRepository):
    def insert_iteration(self, record: dict[str, Any]) -> None:
        data = record if isinstance(record, dict) else {}
        alpha_id = str(data.get("alpha_id") or "")
        created_at = str(data.get("created_at") or data.get("timestamp") or _now())
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO events (source_path, source, event_type, alpha_id, state, created_at, raw_payload)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "workflow/iteration",
                    "workflow",
                    str(data.get("event_type") or "iteration_result"),
                    alpha_id,
                    str(data.get("state") or data.get("status") or ""),
                    created_at,
                    json_dumps_safe(data),
                ),
            )
            self._commit(conn)

    def list_recent_iterations(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT raw_payload FROM events WHERE source='workflow' AND source_path='workflow/iteration' ORDER BY created_at DESC LIMIT ?",
                (max(1, int(limit)),),
            ).fetchall()
            return [json_loads_safe(row[0], {}) for row in rows]


class MLRepository(BaseRepository):
    def __init__(self, conn: sqlite3.Connection | None = None, logger: Any | None = None, *, storage: Any | None = None, db_path: str | Path | None = None) -> None:
        super().__init__(conn, storage=storage, db_path=db_path)
        self.logger = logger

    def insert_training_sample(self, *args: Any, **kwargs: Any) -> bool:
        try:
            if len(args) == 1 and not kwargs:
                sample = args[0]
                if isinstance(sample, dict):
                    data = sample
                else:
                    data = {
                        "sample_id": getattr(sample, "sample_id", ""),
                        "task_name": getattr(sample, "task_name", ""),
                        "alpha_id": getattr(sample, "alpha_id", None),
                        "features": getattr(sample, "features", {}),
                        "label": getattr(sample, "label", {}),
                        "context": getattr(sample, "context", {}),
                        "raw_payload": getattr(sample, "raw_payload", {}),
                    }
                task_name = str(data.get("task_name") or "")
                sample_id = str(data.get("sample_id") or _new_id("ml_sample"))
                alpha_id = data.get("alpha_id")
                features = data.get("features") or {}
                label = data.get("label") or {}
                context = data.get("context") or {}
                raw_payload = data.get("raw_payload") or data.get("raw") or {}
            else:
                names = ["task_name", "sample_id", "alpha_id", "features", "label", "context", "raw_payload"]
                values = {name: args[idx] for idx, name in enumerate(names[: len(args)])}
                values.update(kwargs)
                task_name = str(values.get("task_name") or "")
                sample_id = str(values.get("sample_id") or _new_id("ml_sample"))
                alpha_id = values.get("alpha_id")
                features = values.get("features") or {}
                label = values.get("label") or {}
                context = values.get("context") or {}
                raw_payload = values.get("raw_payload") or {}
            with self.connection() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO ml_training_samples
                    (sample_id, task_name, alpha_id, features_json, label_json, context_json, raw_payload, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (sample_id, task_name, alpha_id, json_dumps_safe(features), json_dumps_safe(label), json_dumps_safe(context), json_dumps_safe(raw_payload), _now()),
                )
                self._commit(conn)
            return True
        except Exception as exc:
            if self.logger is not None:
                try:
                    self.logger.warning("failed to insert ML training sample: %s", exc)
                except Exception:
                    pass
            return False

    def load_training_samples(self, task_name: str, limit: int = 5000) -> list[dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM ml_training_samples WHERE task_name=? ORDER BY created_at DESC LIMIT ?",
                (task_name, max(1, int(limit))),
            ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            row_dict = dict(row) if hasattr(row, "keys") else {}
            row_dict["features"] = json_loads_safe(row_dict.get("features_json"), {})
            row_dict["label"] = json_loads_safe(row_dict.get("label_json"), {})
            row_dict["context"] = json_loads_safe(row_dict.get("context_json"), {})
            row_dict["raw_payload"] = json_loads_safe(row_dict.get("raw_payload"), {})
            row_dict["raw"] = row_dict["raw_payload"]
            result.append(row_dict)
        return result

    def audit_prediction(self, task_name: str, prediction_id: str, alpha_id: str = "", model_version: str = "", features: Any = None, prediction: Any = None, confidence: float | None = None, final_decision: str = "", final_source: str = "", raw_payload: Any = None) -> bool:
        try:
            with self.connection() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO ml_prediction_audit
                    (prediction_id, task_name, alpha_id, model_version, features_json, prediction_json, confidence,
                     final_decision, final_source, created_at, raw_payload)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        prediction_id,
                        task_name,
                        alpha_id,
                        model_version or "",
                        json_dumps_safe(features or {}),
                        json_dumps_safe(prediction or {}),
                        safe_float(confidence),
                        final_decision or "",
                        final_source or "",
                        _now(),
                        json_dumps_safe(raw_payload or {}),
                    ),
                )
                self._commit(conn)
            return True
        except Exception as exc:
            if self.logger is not None:
                try:
                    self.logger.warning("failed to audit ML prediction: %s", exc)
                except Exception:
                    pass
            return False

    def list_model_registry(self, task_name: str | None = None) -> list[dict[str, Any]]:
        try:
            with self.connection() as conn:
                if task_name:
                    rows = conn.execute("SELECT * FROM ml_model_registry WHERE task_name=? ORDER BY created_at DESC", (task_name,)).fetchall()
                else:
                    rows = conn.execute("SELECT * FROM ml_model_registry ORDER BY created_at DESC").fetchall()
            return [dict(row) if hasattr(row, "keys") else {} for row in rows]
        except Exception as exc:
            if self.logger is not None:
                try:
                    self.logger.warning("failed to list ML model registry: %s", exc)
                except Exception:
                    pass
            return []


class DecisionRepository(BaseRepository):
    def insert_decision_snapshot(self, **record: Any) -> str:
        decision_id = str(record.get("decision_id") or _new_id("decision"))
        available = record.get("available_actions")
        if available is None:
            available = []
        elif not isinstance(available, list):
            available = [available]
        with self.connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO decision_snapshots
                (decision_id, decision_type, alpha_id, context_json, available_actions_json, chosen_action_json,
                 action_scores_json, selection_reason, legacy_score, model_score, propensity, model_version, created_at, raw_payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    decision_id,
                    str(record.get("decision_type") or ""),
                    str(record.get("alpha_id") or ""),
                    json_dumps_safe(record.get("context") or {}),
                    json_dumps_safe(available),
                    json_dumps_safe(record.get("chosen_action") or {}),
                    json_dumps_safe(record.get("action_scores") or {}),
                    str(record.get("selection_reason") or ""),
                    safe_float(record.get("legacy_score")),
                    safe_float(record.get("model_score")),
                    safe_float(record.get("propensity")),
                    str(record.get("model_version") or ""),
                    str(record.get("created_at") or _now()),
                    json_dumps_safe(record.get("raw_payload") or {}),
                ),
            )
            self._commit(conn)
        return decision_id

    def insert_decision_outcome(self, **record: Any) -> str:
        outcome_id = str(record.get("outcome_id") or _new_id("outcome"))
        with self.connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO decision_outcomes
                (outcome_id, decision_id, decision_type, alpha_id, reward, reward_delta, success, failure_type,
                 platform_sc_abs_max, metrics_json, created_at, raw_payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    outcome_id,
                    str(record.get("decision_id") or ""),
                    str(record.get("decision_type") or ""),
                    str(record.get("alpha_id") or ""),
                    safe_float(record.get("reward")),
                    safe_float(record.get("reward_delta")),
                    None if record.get("success") is None else (1 if record.get("success") else 0),
                    str(record.get("failure_type") or ""),
                    safe_float(record.get("platform_sc_abs_max")),
                    json_dumps_safe(record.get("metrics") or {}),
                    str(record.get("created_at") or _now()),
                    json_dumps_safe(record.get("raw_payload") or {}),
                ),
            )
            self._commit(conn)
        return outcome_id

    def get_decision(self, decision_id: str) -> dict[str, Any] | None:
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM decision_snapshots WHERE decision_id=?", (decision_id,)).fetchone()
            return dict(row) if row is not None and hasattr(row, "keys") else None

    def list_recent_decisions(self, decision_type: str | None = None, limit: int = 1000) -> list[dict[str, Any]]:
        with self.connection() as conn:
            if decision_type:
                rows = conn.execute("SELECT * FROM decision_snapshots WHERE decision_type=? ORDER BY created_at DESC LIMIT ?", (decision_type, max(1, int(limit)))).fetchall()
            else:
                rows = conn.execute("SELECT * FROM decision_snapshots ORDER BY created_at DESC LIMIT ?", (max(1, int(limit)),)).fetchall()
            return [dict(row) for row in rows if hasattr(row, "keys")]

    def list_outcomes(self, decision_type: str | None = None, limit: int = 5000) -> list[dict[str, Any]]:
        with self.connection() as conn:
            if decision_type:
                rows = conn.execute("SELECT * FROM decision_outcomes WHERE decision_type=? ORDER BY created_at DESC LIMIT ?", (decision_type, max(1, int(limit)))).fetchall()
            else:
                rows = conn.execute("SELECT * FROM decision_outcomes ORDER BY created_at DESC LIMIT ?", (max(1, int(limit)),)).fetchall()
            return [dict(row) for row in rows if hasattr(row, "keys")]

    def get_outcome_for_decision(self, decision_id: str) -> dict[str, Any] | None:
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM decision_outcomes WHERE decision_id=? ORDER BY created_at DESC LIMIT 1", (decision_id,)).fetchone()
            return dict(row) if row is not None and hasattr(row, "keys") else None


class StrategyRepository(BaseRepository):
    def upsert_strategy(self, strategy: dict[str, Any]) -> str:
        data = strategy if isinstance(strategy, dict) else {}
        strategy_id = str(data.get("strategy_id") or _new_id("strategy"))
        now = _now()
        with self.connection() as conn:
            existing = conn.execute("SELECT created_at FROM strategy_registry WHERE strategy_id=?", (strategy_id,)).fetchone()
            conn.execute(
                """
                INSERT INTO strategy_registry
                (strategy_id, strategy_type, role, task_name, model_version, status, created_at, updated_at, raw_payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(strategy_id) DO UPDATE SET
                  strategy_type=excluded.strategy_type,
                  role=excluded.role,
                  task_name=excluded.task_name,
                  model_version=excluded.model_version,
                  status=excluded.status,
                  updated_at=excluded.updated_at,
                  raw_payload=excluded.raw_payload
                """,
                (
                    strategy_id,
                    str(data.get("strategy_type") or ""),
                    str(data.get("role") or "challenger"),
                    str(data.get("task_name") or ""),
                    str(data.get("model_version") or ""),
                    str(data.get("status") or "active"),
                    str(data.get("created_at") or (existing["created_at"] if existing is not None and hasattr(existing, "keys") else now)),
                    str(data.get("updated_at") or now),
                    json_dumps_safe(data),
                ),
            )
            self._commit(conn)
        return strategy_id

    def get_strategy(self, strategy_id: str) -> dict[str, Any] | None:
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM strategy_registry WHERE strategy_id=?", (strategy_id,)).fetchone()
        return self._strategy_row(row)

    def list_strategies(self, status: str | None = None) -> list[dict[str, Any]]:
        with self.connection() as conn:
            if status:
                rows = conn.execute("SELECT * FROM strategy_registry WHERE status=? ORDER BY updated_at DESC", (status,)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM strategy_registry ORDER BY updated_at DESC").fetchall()
        return [r for r in (self._strategy_row(row) for row in rows) if r is not None]

    def list_by_role(self, role: str, task_name: str | None = None) -> list[dict[str, Any]]:
        with self.connection() as conn:
            if task_name:
                rows = conn.execute(
                    "SELECT * FROM strategy_registry WHERE role=? AND status='active' AND (task_name=? OR task_name='') ORDER BY updated_at DESC",
                    (role, task_name),
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM strategy_registry WHERE role=? AND status='active' ORDER BY updated_at DESC", (role,)).fetchall()
        return [r for r in (self._strategy_row(row) for row in rows) if r is not None]

    def update_role(self, strategy_id: str, role: str, reason: str = "") -> None:
        with self.connection() as conn:
            row = conn.execute("SELECT raw_payload FROM strategy_registry WHERE strategy_id=?", (strategy_id,)).fetchone()
            payload = json_loads_safe(row["raw_payload"] if row is not None and hasattr(row, "keys") else None, {})
            if not isinstance(payload, dict):
                payload = {}
            payload.update({"role": role, "last_role_change_reason": reason, "updated_at": _now()})
            conn.execute(
                "UPDATE strategy_registry SET role=?, updated_at=?, raw_payload=? WHERE strategy_id=?",
                (role, payload["updated_at"], json_dumps_safe(payload), strategy_id),
            )
            self._commit(conn)

    def deactivate_strategy(self, strategy_id: str, reason: str = "") -> None:
        with self.connection() as conn:
            row = conn.execute("SELECT raw_payload FROM strategy_registry WHERE strategy_id=?", (strategy_id,)).fetchone()
            payload = json_loads_safe(row["raw_payload"] if row is not None and hasattr(row, "keys") else None, {})
            if not isinstance(payload, dict):
                payload = {}
            payload.update({"status": "inactive", "deactivate_reason": reason, "updated_at": _now()})
            conn.execute(
                "UPDATE strategy_registry SET status='inactive', updated_at=?, raw_payload=? WHERE strategy_id=?",
                (payload["updated_at"], json_dumps_safe(payload), strategy_id),
            )
            self._commit(conn)

    def insert_allocation(self, allocation: dict[str, Any]) -> str:
        data = allocation if isinstance(allocation, dict) else {}
        allocation_id = str(data.get("allocation_id") or _new_id("allocation"))
        with self.connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO strategy_allocations
                (allocation_id, strategy_id, role, budget, effective_from, effective_to, reason, created_at, raw_payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    allocation_id,
                    str(data.get("strategy_id") or ""),
                    str(data.get("role") or ""),
                    safe_float(data.get("budget"), 0.0),
                    str(data.get("effective_from") or _now()),
                    str(data.get("effective_to") or ""),
                    str(data.get("reason") or ""),
                    str(data.get("created_at") or _now()),
                    json_dumps_safe(data),
                ),
            )
            self._commit(conn)
        return allocation_id

    def latest_allocations(self) -> list[dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT a.* FROM strategy_allocations a
                JOIN (SELECT strategy_id, MAX(created_at) AS max_created FROM strategy_allocations GROUP BY strategy_id) b
                  ON a.strategy_id=b.strategy_id AND a.created_at=b.max_created
                ORDER BY a.created_at DESC
                """
            ).fetchall()
        return [dict(row) for row in rows if hasattr(row, "keys")]

    def insert_strategy_decision(self, decision: dict[str, Any]) -> str:
        data = decision if isinstance(decision, dict) else {}
        decision_id = str(data.get("decision_id") or _new_id("strategy_decision"))
        with self.connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO strategy_decisions
                (decision_id, strategy_id, alpha_id, decision_type, selected, shadow, score, model_version, created_at, raw_payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    decision_id,
                    str(data.get("strategy_id") or ""),
                    str(data.get("alpha_id") or ""),
                    str(data.get("decision_type") or ""),
                    1 if data.get("selected") else 0,
                    1 if data.get("shadow") else 0,
                    safe_float(data.get("score")),
                    str(data.get("model_version") or ""),
                    str(data.get("created_at") or _now()),
                    json_dumps_safe(data),
                ),
            )
            self._commit(conn)
        return decision_id

    def list_strategy_decisions(self, strategy_id: str | None = None, limit: int = 1000) -> list[dict[str, Any]]:
        with self.connection() as conn:
            if strategy_id:
                rows = conn.execute("SELECT * FROM strategy_decisions WHERE strategy_id=? ORDER BY created_at DESC LIMIT ?", (strategy_id, max(1, int(limit)))).fetchall()
            else:
                rows = conn.execute("SELECT * FROM strategy_decisions ORDER BY created_at DESC LIMIT ?", (max(1, int(limit)),)).fetchall()
        return [dict(row) for row in rows if hasattr(row, "keys")]

    def insert_performance(self, record: dict[str, Any]) -> str:
        data = record if isinstance(record, dict) else {}
        record_id = str(data.get("record_id") or _new_id("strategy_perf"))
        perf = data.get("performance") if isinstance(data.get("performance"), dict) else data.get("performance_json", {})
        with self.connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO strategy_performance
                (record_id, strategy_id, window_name, sample_count, avg_reward, median_reward, success_rate, failure_rate,
                 avg_platform_sc_abs_max, avg_turnover, avg_fitness, performance_json, created_at, raw_payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record_id,
                    str(data.get("strategy_id") or ""),
                    str(data.get("window_name") or "recent"),
                    safe_int(data.get("sample_count"), 0),
                    safe_float(data.get("avg_reward"), 0.0),
                    safe_float(data.get("median_reward"), 0.0),
                    safe_float(data.get("success_rate"), 0.0),
                    safe_float(data.get("failure_rate"), 0.0),
                    safe_float(data.get("avg_platform_sc_abs_max"), 0.0),
                    safe_float(data.get("avg_turnover"), 0.0),
                    safe_float(data.get("avg_fitness"), 0.0),
                    json_dumps_safe(perf or {}),
                    str(data.get("created_at") or _now()),
                    json_dumps_safe(data),
                ),
            )
            self._commit(conn)
        return record_id

    def latest_performance(self, strategy_id: str, window_name: str | None = None) -> dict[str, Any] | None:
        with self.connection() as conn:
            if window_name:
                row = conn.execute("SELECT * FROM strategy_performance WHERE strategy_id=? AND window_name=? ORDER BY created_at DESC LIMIT 1", (strategy_id, window_name)).fetchone()
            else:
                row = conn.execute("SELECT * FROM strategy_performance WHERE strategy_id=? ORDER BY created_at DESC LIMIT 1", (strategy_id,)).fetchone()
        return dict(row) if row is not None and hasattr(row, "keys") else None

    def _strategy_row(self, row: Any) -> dict[str, Any] | None:
        if row is None or not hasattr(row, "keys"):
            return None
        data = dict(row)
        payload = json_loads_safe(data.get("raw_payload"), {})
        if isinstance(payload, dict):
            payload.update({k: v for k, v in data.items() if k != "raw_payload"})
            return payload
        return data


class ReplayReportRepository(BaseRepository):
    def insert_offline_replay_report(self, report: dict[str, Any]) -> str:
        data = report if isinstance(report, dict) else {}
        report_id = str(data.get("report_id") or _new_id("replay_report"))
        with self.connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO offline_replay_reports
                (report_id, task_name, strategy_id, model_version, decision_type, sample_count, support_coverage,
                 model_match_rate, estimated_reward_delta, estimated_risk_delta, replay_pass, report_json, created_at, raw_payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report_id,
                    str(data.get("task_name") or ""),
                    str(data.get("strategy_id") or ""),
                    str(data.get("model_version") or ""),
                    str(data.get("decision_type") or ""),
                    safe_int(data.get("sample_count"), 0),
                    safe_float(data.get("support_coverage"), 0.0),
                    safe_float(data.get("model_match_rate"), 0.0),
                    safe_float(data.get("estimated_reward_delta"), 0.0),
                    safe_float(data.get("estimated_sc_risk_delta", data.get("estimated_risk_delta")), 0.0),
                    1 if data.get("replay_pass") else 0,
                    json_dumps_safe(data.get("report_json") or data),
                    str(data.get("created_at") or _now()),
                    json_dumps_safe(data.get("raw_payload") or data),
                ),
            )
            self._commit(conn)
        return report_id

    def latest_offline_replay_report(self, task_name: str | None = None, strategy_id: str | None = None, decision_type: str | None = None) -> dict[str, Any] | None:
        clauses: list[str] = []
        params: list[Any] = []
        if task_name:
            clauses.append("task_name=?"); params.append(task_name)
        if strategy_id:
            clauses.append("strategy_id=?"); params.append(strategy_id)
        if decision_type:
            clauses.append("decision_type=?"); params.append(decision_type)
        sql = "SELECT * FROM offline_replay_reports"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at DESC LIMIT 1"
        with self.connection() as conn:
            row = conn.execute(sql, tuple(params)).fetchone()
        if row is None or not hasattr(row, "keys"):
            return None
        data = dict(row)
        report = json_loads_safe(data.get("report_json"), {})
        if isinstance(report, dict):
            report.update({k: v for k, v in data.items() if k not in {"report_json", "raw_payload"}})
            report["replay_pass"] = bool(data.get("replay_pass"))
            return report
        return data

    def insert_policy_replay_evaluation(self, evaluation: dict[str, Any]) -> str:
        data = evaluation if isinstance(evaluation, dict) else {}
        evaluation_id = str(data.get("evaluation_id") or _new_id("policy_replay"))
        with self.connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO policy_replay_evaluations
                (evaluation_id, task_name, model_version, decision_type, sample_count, support_coverage, action_coverage,
                 avg_legacy_score, avg_model_score, estimated_reward_delta, estimated_sc_risk_delta, estimated_failure_delta,
                 evaluation_json, created_at, raw_payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    evaluation_id,
                    str(data.get("task_name") or ""),
                    str(data.get("model_version") or ""),
                    str(data.get("decision_type") or ""),
                    safe_int(data.get("sample_count"), 0),
                    safe_float(data.get("support_coverage"), 0.0),
                    safe_float(data.get("action_coverage"), 0.0),
                    safe_float(data.get("avg_legacy_score"), 0.0),
                    safe_float(data.get("avg_model_score"), 0.0),
                    safe_float(data.get("estimated_reward_delta"), 0.0),
                    safe_float(data.get("estimated_sc_risk_delta"), 0.0),
                    safe_float(data.get("estimated_failure_delta"), 0.0),
                    json_dumps_safe(data.get("evaluation_json") or data),
                    str(data.get("created_at") or _now()),
                    json_dumps_safe(data.get("raw_payload") or data),
                ),
            )
            self._commit(conn)
        return evaluation_id

    def insert_model_safety_report(self, report: dict[str, Any]) -> str:
        data = report if isinstance(report, dict) else {}
        report_id = str(data.get("report_id") or _new_id("safety_report"))
        reasons = data.get("reasons") if isinstance(data.get("reasons"), list) else []
        reason = str(data.get("reason") or ",".join(str(r) for r in reasons))
        with self.connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO model_safety_reports
                (report_id, task_name, model_version, strategy_id, validation_pass, replay_pass, support_pass,
                 promotion_pass, safety_status, reason, report_json, created_at, raw_payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report_id,
                    str(data.get("task_name") or ""),
                    str(data.get("model_version") or ""),
                    str(data.get("strategy_id") or ""),
                    1 if data.get("validation_pass") else 0,
                    1 if data.get("replay_pass") else 0,
                    1 if data.get("support_pass") else 0,
                    1 if data.get("promotion_pass") else 0,
                    str(data.get("safety_status") or ("pass" if data.get("safety_pass") else "fail")),
                    reason,
                    json_dumps_safe(data.get("report_json") or data),
                    str(data.get("created_at") or _now()),
                    json_dumps_safe(data.get("raw_payload") or data),
                ),
            )
            self._commit(conn)
        return report_id

    def latest_model_safety_report(self, strategy_id: str | None = None, task_name: str | None = None, model_version: str | None = None) -> dict[str, Any] | None:
        clauses: list[str] = []
        params: list[Any] = []
        if strategy_id:
            clauses.append("strategy_id=?"); params.append(strategy_id)
        if task_name:
            clauses.append("task_name=?"); params.append(task_name)
        if model_version:
            clauses.append("model_version=?"); params.append(model_version)
        sql = "SELECT * FROM model_safety_reports"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at DESC LIMIT 1"
        with self.connection() as conn:
            row = conn.execute(sql, tuple(params)).fetchone()
        if row is None or not hasattr(row, "keys"):
            return None
        data = dict(row)
        report = json_loads_safe(data.get("report_json"), {})
        if isinstance(report, dict):
            report.update({k: v for k, v in data.items() if k not in {"report_json", "raw_payload"}})
            report["validation_pass"] = bool(data.get("validation_pass"))
            report["replay_pass"] = bool(data.get("replay_pass"))
            report["support_pass"] = bool(data.get("support_pass"))
            report["promotion_pass"] = bool(data.get("promotion_pass"))
            report["safety_pass"] = str(data.get("safety_status") or "").lower() in {"pass", "passed", "safe"}
            return report
        return data


class ExperimentRepository(BaseRepository):
    def insert_experiment(self, record: dict[str, Any]) -> str:
        data = record if isinstance(record, dict) else {}
        experiment_id = str(data.get("experiment_id") or _new_id("experiment"))
        with self.connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO experiment_records
                (experiment_id, experiment_type, base_alpha_id, controlled_variable, hypothesis, status, created_at, raw_payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (experiment_id, str(data.get("experiment_type") or ""), str(data.get("base_alpha_id") or ""), str(data.get("controlled_variable") or ""), str(data.get("hypothesis") or ""), str(data.get("status") or "open"), str(data.get("created_at") or _now()), json_dumps_safe(data)),
            )
            self._commit(conn)
        return experiment_id

    def update_experiment_status(self, experiment_id: str, status: str) -> None:
        with self.connection() as conn:
            conn.execute("UPDATE experiment_records SET status=? WHERE experiment_id=?", (status, experiment_id))
            self._commit(conn)

    def list_open_experiments(self) -> list[dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute("SELECT * FROM experiment_records WHERE status NOT IN ('closed','done','failed') ORDER BY created_at DESC").fetchall()
            return [dict(row) for row in rows if hasattr(row, "keys")]


class InsightRepository(BaseRepository):
    def insert_usage(self, insight_id: str, alpha_id: str = "", prompt_context: Any = None, raw_payload: Any = None) -> str:
        usage_id = _new_id("insight_usage")
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO insight_usage (usage_id, insight_id, alpha_id, prompt_context_json, created_at, raw_payload)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (usage_id, insight_id, alpha_id, json_dumps_safe(prompt_context or {}), _now(), json_dumps_safe(raw_payload or {})),
            )
            self._commit(conn)
        return usage_id

    def insert_effect(self, insight_id: str, alpha_id: str = "", reward: Any = None, fitness: Any = None, sharpe: Any = None, turnover: Any = None, platform_sc_abs_max: Any = None, raw_payload: Any = None) -> str:
        effect_id = _new_id("insight_effect")
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO insight_effect_samples
                (effect_id, insight_id, alpha_id, reward, fitness, sharpe, turnover, platform_sc_abs_max, created_at, raw_payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (effect_id, insight_id, alpha_id, safe_float(reward), safe_float(fitness), safe_float(sharpe), safe_float(turnover), safe_float(platform_sc_abs_max), _now(), json_dumps_safe(raw_payload or {})),
            )
            self._commit(conn)
        return effect_id

    def load_effects(self, insight_id: str) -> list[dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute("SELECT * FROM insight_effect_samples WHERE insight_id=? ORDER BY created_at DESC", (insight_id,)).fetchall()
            return [dict(row) for row in rows if hasattr(row, "keys")]


class DriftRepository(BaseRepository):
    def insert_drift_event(self, event: dict[str, Any]) -> str:
        data = event if isinstance(event, dict) else {}
        event_id = str(data.get("event_id") or _new_id("drift"))
        with self.connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO drift_events
                (event_id, drift_type, severity, metric_name, event_json, created_at, raw_payload)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (event_id, str(data.get("drift_type") or data.get("event_type") or ""), str(data.get("severity") or "info"), str(data.get("metric_name") or ""), json_dumps_safe(data.get("event") or data), str(data.get("created_at") or _now()), json_dumps_safe(data)),
            )
            self._commit(conn)
        return event_id

    def list_recent_events(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute("SELECT * FROM drift_events ORDER BY created_at DESC LIMIT ?", (max(1, int(limit)),)).fetchall()
            return [dict(row) for row in rows if hasattr(row, "keys")]


@dataclass
class RepositoryBundle:
    candidate: CandidateRepository
    iteration: IterationRepository
    ml: MLRepository
    decision: DecisionRepository
    experiment: ExperimentRepository
    insight: InsightRepository
    drift: DriftRepository
    strategy: StrategyRepository
    replay: ReplayReportRepository

    @classmethod
    def from_storage(cls, *, storage: Any | None = None, db_path: str | Path | None = None, conn: sqlite3.Connection | None = None) -> "RepositoryBundle":
        kwargs = {"storage": storage, "db_path": db_path, "conn": conn}
        return cls(
            candidate=CandidateRepository(**kwargs),
            iteration=IterationRepository(**kwargs),
            ml=MLRepository(**kwargs),
            decision=DecisionRepository(**kwargs),
            experiment=ExperimentRepository(**kwargs),
            insight=InsightRepository(**kwargs),
            drift=DriftRepository(**kwargs),
            strategy=StrategyRepository(**kwargs),
            replay=ReplayReportRepository(**kwargs),
        )


# ---- Phase 2 v2_refactor repository interface compatibility ----
def _phase2_repository_compat() -> None:
    def save_candidate(self, candidate_record):
        return self.upsert_candidate(candidate_record)

    def load_candidates(self, limit=100, **_filters):
        return self.list_recent_candidates(limit=limit)

    def select_parent_candidates(self, limit=100, **_filters):
        return self.list_recent_candidates(limit=limit)

    def update_candidate(self, alpha_id, updates=None, **kwargs):
        record = self.get_candidate(alpha_id) or {"alpha_id": alpha_id}
        if isinstance(updates, dict):
            record.update(updates)
        record.update(kwargs)
        record["alpha_id"] = alpha_id
        self.upsert_candidate(record)
        return True

    def rebuild_from_sqlite_if_json_broken(self, *args, **kwargs):
        return {"ok": True, "rebuilt": False, "reason": "sqlite_repository_authoritative"}

    def append_iteration(self, record):
        return self.insert_iteration(record)

    def append_workflow_event(self, record):
        return self.insert_iteration(record)

    CandidateRepository.save_candidate = save_candidate
    CandidateRepository.load_candidates = load_candidates
    CandidateRepository.select_parent_candidates = select_parent_candidates
    CandidateRepository.update_candidate = update_candidate
    CandidateRepository.rebuild_from_sqlite_if_json_broken = rebuild_from_sqlite_if_json_broken
    IterationRepository.append_iteration = append_iteration
    IterationRepository.append_workflow_event = append_workflow_event
    IterationRepository.load_recent_iterations = IterationRepository.list_recent_iterations


_phase2_repository_compat()
