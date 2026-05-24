from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, default=str)


def _payload(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number != number or number in {float("inf"), float("-inf")}:
        return default
    return number


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def source_path_for(path: str | Path, *, root: str | Path | None = None) -> str:
    path = Path(path)
    if root is not None:
        try:
            return path.resolve().relative_to(Path(root).resolve()).as_posix()
        except OSError:
            pass
        except ValueError:
            pass
    return str(path)


def event_metadata(source_path: str, payload: dict[str, Any]) -> dict[str, str]:
    lower = source_path.replace("\\", "/").lower()
    source = "workflow"
    if "migration" in lower or payload.get("action") in {"rollback", "transition", "blend"}:
        source = "migration"
    elif "reward" in lower or "legacy_reward" in payload or "v2_reward" in payload:
        source = "reward"
    elif "candidate_pool" in lower:
        source = "candidate"
    elif "alpha_lineage" in lower or "lineage" in lower:
        source = "population"
    elif "workflow_state" in lower:
        source = "simulate"
    elif lower.endswith(".csv"):
        source = "simulate"

    event_type = str(
        payload.get("event")
        or payload.get("action")
        or payload.get("mutation_type")
        or ("snapshot" if lower.endswith(".json") else "log")
    )
    return {
        "source": source,
        "event_type": event_type,
        "alpha_id": str(payload.get("alpha_id") or payload.get("alpha_name") or ""),
        "state": str(payload.get("state") or payload.get("current_state") or ""),
        "created_at": str(payload.get("time") or payload.get("timestamp") or payload.get("created_at") or _now()),
    }


class AlphaRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def insert_alpha(self, payload: dict[str, Any] | None = None, **fields: Any) -> None:
        data = {**(payload or {}), **fields}
        metrics = data.get("metrics") if isinstance(data.get("metrics"), dict) else {}
        alpha_id = str(data.get("alpha_id") or data.get("alpha_name") or "")
        expression = str(data.get("expression") or data.get("code") or data.get("expression_after") or "")
        score = _float(data.get("score", data.get("reward", data.get("final_reward", 0.0))))
        result = data.get("result")
        if result is None and "passed" in data:
            result = "passed" if data.get("passed") else "failed"
        self.conn.execute(
            """
            INSERT OR IGNORE INTO alpha_runs
            (alpha_id, expression, fitness, sharpe, turnover, margin, score, result, created_at, raw_payload)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                alpha_id or None,
                expression,
                _float(data.get("fitness", metrics.get("fitness"))),
                _float(data.get("sharpe", metrics.get("sharpe"))),
                _float(data.get("turnover", metrics.get("turnover"))),
                _float(data.get("margin", metrics.get("margin"))),
                score,
                str(result or ""),
                str(data.get("created_at") or data.get("timestamp") or data.get("time") or _now()),
                _json(data),
            ),
        )

    def batch_insert(self, rows: Iterable[dict[str, Any]]) -> None:
        for row in rows:
            self.insert_alpha(row)

    def get_alpha(self, alpha_id: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM alpha_runs WHERE alpha_id = ?", (alpha_id,)).fetchone()
        if row is None:
            return None
        payload = _payload(row["raw_payload"])
        payload.update(
            {
                "alpha_id": row["alpha_id"],
                "expression": row["expression"],
                "fitness": row["fitness"],
                "sharpe": row["sharpe"],
                "turnover": row["turnover"],
                "margin": row["margin"],
                "score": row["score"],
                "result": row["result"],
                "created_at": row["created_at"],
            }
        )
        return payload

    def update_score(self, alpha_id: str, score: float) -> None:
        self.conn.execute("UPDATE alpha_runs SET score = ? WHERE alpha_id = ?", (_float(score), alpha_id))


class LineageRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def add_lineage(
        self,
        child_alpha: str = "",
        parent_alpha: str = "",
        mutation_type: str = "",
        operator_name: str = "",
        created_at: str = "",
        payload: dict[str, Any] | None = None,
    ) -> None:
        data = payload or {}
        child = child_alpha or str(data.get("child_alpha") or data.get("alpha_id") or "")
        parent = parent_alpha or str(data.get("parent_alpha") or data.get("parent_id") or data.get("parent") or "")
        mutation = mutation_type or str(data.get("mutation_type") or "")
        operator = operator_name or str(data.get("operator_name") or data.get("operator") or mutation)
        self.conn.execute(
            """
            INSERT INTO lineage (child_alpha, parent_alpha, mutation_type, operator_name, created_at, raw_payload)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (child, parent, mutation, operator, created_at or str(data.get("timestamp") or data.get("created_at") or _now()), _json(data)),
        )

    def get_parents(self, child_alpha: str, *, limit: int = 20) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM lineage WHERE child_alpha = ? ORDER BY id DESC LIMIT ?",
            (child_alpha, max(1, int(limit))),
        ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            payload = _payload(row["raw_payload"])
            payload.update(
                {
                    "child_alpha": row["child_alpha"],
                    "parent_alpha": row["parent_alpha"],
                    "mutation_type": row["mutation_type"],
                    "operator_name": row["operator_name"],
                    "created_at": row["created_at"],
                }
            )
            result.append(payload)
        return result

    def latest(self, *, limit: int = 2000) -> list[dict[str, Any]]:
        rows = self.conn.execute("SELECT raw_payload FROM lineage ORDER BY id DESC LIMIT ?", (max(1, int(limit)),)).fetchall()
        return list(reversed([_payload(row["raw_payload"]) for row in rows]))


class OperatorStatsRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def upsert_operator(self, operator_name: str, payload: dict[str, Any]) -> None:
        success = _int(payload.get("success_count", payload.get("success", 0)))
        fail = _int(payload.get("fail_count", max(0, _int(payload.get("count", 0)) - success)))
        avg_reward = _float(payload.get("avg_reward", payload.get("success_rate", 0.0)))
        self.conn.execute(
            """
            INSERT INTO operator_stats (operator_name, success_count, fail_count, avg_reward, last_used, raw_payload)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(operator_name) DO UPDATE SET
              success_count = excluded.success_count,
              fail_count = excluded.fail_count,
              avg_reward = excluded.avg_reward,
              last_used = excluded.last_used,
              raw_payload = excluded.raw_payload
            """,
            (operator_name, success, fail, avg_reward, str(payload.get("last_used") or _now()), _json(payload)),
        )

    def replace_from_mapping(self, stats: dict[str, Any]) -> None:
        for name, payload in stats.items():
            if isinstance(payload, dict):
                self.upsert_operator(str(name), payload)

    def get_all(self) -> dict[str, dict[str, Any]]:
        rows = self.conn.execute("SELECT operator_name, raw_payload FROM operator_stats ORDER BY operator_name").fetchall()
        return {str(row["operator_name"]): _payload(row["raw_payload"]) for row in rows}


class StateTransitionRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def add_transition(self, payload: dict[str, Any]) -> None:
        self.conn.execute(
            """
            INSERT INTO state_transitions (alpha_id, state_name, status, error, created_at, raw_payload)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                str(payload.get("alpha_id") or ""),
                str(payload.get("state") or payload.get("state_name") or ""),
                str(payload.get("event") or payload.get("status") or ""),
                str(payload.get("error") or ""),
                str(payload.get("time") or payload.get("timestamp") or payload.get("created_at") or _now()),
                _json(payload),
            ),
        )

    def tail(self, *, limit: int = 2000) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT raw_payload FROM state_transitions ORDER BY id DESC LIMIT ?",
            (max(1, int(limit)),),
        ).fetchall()
        return list(reversed([_payload(row["raw_payload"]) for row in rows]))


class EvolutionMemoryRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def set_memory(self, namespace: str, memory_key: str, memory_value: Any, *, score: float = 0.0, created_at: str = "") -> None:
        self.conn.execute(
            """
            INSERT INTO evolution_memory (namespace, memory_key, memory_value, score, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(namespace, memory_key) DO UPDATE SET
              memory_value = excluded.memory_value,
              score = excluded.score,
              created_at = excluded.created_at
            """,
            (namespace or "legacy", memory_key, _json(memory_value), _float(score), created_at or _now()),
        )

    def replace_namespace(self, namespace: str, mapping: dict[str, Any]) -> None:
        self.conn.execute("DELETE FROM evolution_memory WHERE namespace = ?", (namespace,))
        for key, value in mapping.items():
            score = _float(value.get("score", value.get("reward", 0.0))) if isinstance(value, dict) else 0.0
            self.set_memory(namespace, str(key), value, score=score)

    def get_memory(self, namespace: str, memory_key: str, default: Any = None) -> Any:
        row = self.conn.execute(
            "SELECT memory_value FROM evolution_memory WHERE namespace = ? AND memory_key = ?",
            (namespace or "legacy", memory_key),
        ).fetchone()
        if row is None:
            return default
        try:
            return json.loads(row["memory_value"])
        except json.JSONDecodeError:
            return default

    def list_namespace(self, namespace: str) -> dict[str, Any]:
        rows = self.conn.execute(
            "SELECT memory_key, memory_value FROM evolution_memory WHERE namespace = ? ORDER BY memory_key",
            (namespace or "legacy",),
        ).fetchall()
        result: dict[str, Any] = {}
        for row in rows:
            try:
                result[str(row["memory_key"])] = json.loads(row["memory_value"])
            except json.JSONDecodeError:
                result[str(row["memory_key"])] = row["memory_value"]
        return result


class CandidatePoolRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.alpha_repo = AlphaRepository(conn)

    def upsert_candidate(self, payload: dict[str, Any]) -> None:
        alpha_id = str(payload.get("alpha_id") or "")
        if not alpha_id:
            return
        metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
        reward = _float(payload.get("reward", payload.get("score", 0.0)))
        updated_at = str(payload.get("updated_at") or payload.get("timestamp") or payload.get("created_at") or _now())
        self.conn.execute(
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
                str(payload.get("expression") or payload.get("code") or ""),
                reward,
                _float(payload.get("score", reward)),
                1 if payload.get("passed") or payload.get("template_success") else 0,
                str(payload.get("created_at") or payload.get("timestamp") or _now()),
                updated_at,
                _json(payload),
            ),
        )
        self.alpha_repo.insert_alpha(
            {
                **payload,
                "fitness": metrics.get("fitness"),
                "sharpe": metrics.get("sharpe"),
                "turnover": metrics.get("turnover"),
                "score": reward,
            }
        )

    def replace_candidates(self, rows: list[dict[str, Any]]) -> None:
        self.conn.execute("DELETE FROM candidate_pool")
        for row in rows:
            if isinstance(row, dict):
                self.upsert_candidate(row)

    def list_candidates(self, *, limit: int = 2000) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT raw_payload FROM candidate_pool ORDER BY score DESC, updated_at DESC LIMIT ?",
            (max(1, int(limit)),),
        ).fetchall()
        return [_payload(row["raw_payload"]) for row in rows]


class FailurePatternRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def insert_failure(self, payload: dict[str, Any]) -> None:
        self.conn.execute(
            """
            INSERT INTO failure_patterns (error_type, expression, root_cause, successful_fix, created_at, raw_payload)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                str(payload.get("error_type") or payload.get("failure_type") or ""),
                str(payload.get("expression") or ""),
                str(payload.get("root_cause") or payload.get("failure_reason") or ""),
                str(payload.get("successful_fix") or ""),
                str(payload.get("timestamp") or payload.get("created_at") or _now()),
                _json(payload),
            ),
        )

    def replace_failures(self, rows: list[dict[str, Any]]) -> None:
        self.conn.execute("DELETE FROM failure_patterns")
        for row in rows:
            if isinstance(row, dict):
                self.insert_failure(row)

    def list_failures(self, *, limit: int = 1000) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT raw_payload FROM failure_patterns ORDER BY id DESC LIMIT ?",
            (max(1, int(limit)),),
        ).fetchall()
        return list(reversed([_payload(row["raw_payload"]) for row in rows]))


class EventRepository:
    def __init__(self, conn: sqlite3.Connection, *, root: str | Path | None = None) -> None:
        self.conn = conn
        self.root = root

    def insert_event(self, source_path: str | Path, payload: dict[str, Any]) -> None:
        self.batch_insert_events([(source_path, payload)])

    def batch_insert_events(self, rows: Iterable[tuple[str | Path, dict[str, Any]]]) -> None:
        event_rows: list[tuple[str, str, str, str, str, str, str]] = []
        state_rows: list[tuple[str, str, str, str, str, str]] = []
        for path, payload in rows:
            if not isinstance(payload, dict):
                continue
            rel = source_path_for(path, root=self.root)
            meta = event_metadata(rel, payload)
            event_rows.append(
                (
                    rel,
                    meta["source"],
                    meta["event_type"],
                    meta["alpha_id"],
                    meta["state"],
                    meta["created_at"],
                    _json(payload),
                )
            )
            if "workflow_state" in rel.replace("\\", "/").lower() or meta["event_type"].startswith("STATE_"):
                state_rows.append(
                    (
                        meta["alpha_id"],
                        meta["state"],
                        meta["event_type"],
                        str(payload.get("error") or ""),
                        meta["created_at"],
                        _json(payload),
                    )
                )
        if event_rows:
            self.conn.executemany(
                """
                INSERT INTO events (source_path, source, event_type, alpha_id, state, created_at, raw_payload)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                event_rows,
            )
        if state_rows:
            self.conn.executemany(
                """
                INSERT INTO state_transitions (alpha_id, state_name, status, error, created_at, raw_payload)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                state_rows,
            )

    def tail_for_path(self, source_path: str | Path, *, limit: int = 2000) -> list[dict[str, Any]]:
        rel = source_path_for(source_path, root=self.root)
        rows = self.conn.execute(
            "SELECT raw_payload FROM events WHERE source_path = ? ORDER BY id DESC LIMIT ?",
            (rel, max(1, int(limit))),
        ).fetchall()
        return list(reversed([_payload(row["raw_payload"]) for row in rows]))

    def query(
        self,
        *,
        alpha_id: str = "",
        source: str = "",
        event_type: str = "",
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if alpha_id:
            clauses.append("alpha_id = ?")
            params.append(alpha_id)
        if source:
            clauses.append("source = ?")
            params.append(source)
        if event_type:
            clauses.append("event_type = ?")
            params.append(event_type)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        rows = self.conn.execute(
            f"SELECT raw_payload FROM events{where} ORDER BY id DESC LIMIT ?",
            [*params, max(1, int(limit))],
        ).fetchall()
        return list(reversed([_payload(row["raw_payload"]) for row in rows]))


class OffsetRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def get_offset(self, source_path: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM storage_offsets WHERE source_path = ?", (source_path,)).fetchone()
        return dict(row) if row is not None else None

    def set_offset(self, source_path: str, *, size: int, mtime: float, line_no: int) -> None:
        self.conn.execute(
            """
            INSERT INTO storage_offsets (source_path, size, mtime, line_no, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(source_path) DO UPDATE SET
              size = excluded.size,
              mtime = excluded.mtime,
              line_no = excluded.line_no,
              updated_at = excluded.updated_at
            """,
            (source_path, int(size), float(mtime), int(line_no), _now()),
        )
