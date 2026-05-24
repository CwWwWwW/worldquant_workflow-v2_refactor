from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .repository import EventRepository
from .schema import initialize_schema
from .sqlite_store import connect_db


def query_events(
    db_path: str | Path,
    *,
    alpha_id: str = "",
    source: str = "",
    event_type: str = "",
    limit: int = 1000,
) -> list[dict[str, Any]]:
    conn = connect_db(db_path)
    try:
        initialize_schema(conn)
        return EventRepository(conn).query(alpha_id=alpha_id, source=source, event_type=event_type, limit=limit)
    finally:
        conn.close()


def export_memory_snapshot(
    db_path: str | Path,
    *,
    alpha_id: str = "",
    limit: int = 5000,
) -> dict[str, Any]:
    conn = connect_db(db_path)
    try:
        initialize_schema(conn)
        return {
            "schema": "workflow_sqlite_snapshot_v1",
            "alpha_runs": _table_payloads(conn, "alpha_runs", alpha_id=alpha_id, limit=limit),
            "lineage": _table_payloads(conn, "lineage", alpha_id=alpha_id, limit=limit),
            "operator_stats": _operator_stats(conn),
            "candidate_pool": _table_payloads(conn, "candidate_pool", alpha_id=alpha_id, limit=limit),
            "failure_patterns": _table_payloads(conn, "failure_patterns", limit=limit),
            "evolution_memory": _evolution_memory(conn, limit=limit),
            "events": _events(conn, alpha_id=alpha_id, limit=limit),
        }
    finally:
        conn.close()


def _table_payloads(conn, table: str, *, alpha_id: str = "", limit: int = 5000) -> list[dict[str, Any]]:
    where = ""
    params: list[Any] = []
    if alpha_id and table in {"alpha_runs", "candidate_pool"}:
        where = " WHERE alpha_id = ?"
        params.append(alpha_id)
    elif alpha_id and table == "lineage":
        where = " WHERE child_alpha = ? OR parent_alpha = ?"
        params.extend([alpha_id, alpha_id])
    rows = conn.execute(
        f"SELECT raw_payload FROM {table}{where} ORDER BY rowid DESC LIMIT ?",
        [*params, max(1, int(limit))],
    ).fetchall()
    return list(reversed([_payload(row["raw_payload"]) for row in rows]))


def _operator_stats(conn) -> dict[str, Any]:
    rows = conn.execute("SELECT operator_name, raw_payload FROM operator_stats ORDER BY operator_name").fetchall()
    return {str(row["operator_name"]): _payload(row["raw_payload"]) for row in rows}


def _evolution_memory(conn, *, limit: int) -> dict[str, Any]:
    rows = conn.execute(
        "SELECT namespace, memory_key, memory_value, score, created_at FROM evolution_memory ORDER BY id DESC LIMIT ?",
        (max(1, int(limit)),),
    ).fetchall()
    result: dict[str, Any] = {}
    for row in reversed(rows):
        namespace = str(row["namespace"] or "legacy")
        bucket = result.setdefault(namespace, {})
        try:
            value = json.loads(row["memory_value"])
        except json.JSONDecodeError:
            value = row["memory_value"]
        bucket[str(row["memory_key"])] = {
            "value": value,
            "score": row["score"],
            "created_at": row["created_at"],
        }
    return result


def _events(conn, *, alpha_id: str, limit: int) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if alpha_id:
        clauses.append("alpha_id = ?")
        params.append(alpha_id)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    rows = conn.execute(
        f"SELECT source_path, source, event_type, alpha_id, state, created_at, raw_payload FROM events{where} ORDER BY id DESC LIMIT ?",
        [*params, max(1, int(limit))],
    ).fetchall()
    result: list[dict[str, Any]] = []
    for row in reversed(rows):
        result.append(
            {
                "timestamp": row["created_at"],
                "source": row["source"],
                "event_type": row["event_type"],
                "alpha_id": row["alpha_id"],
                "state": row["state"],
                "payload": _payload(row["raw_payload"]),
                "original_path": row["source_path"],
                "line_no": 0,
            }
        )
    return result


def _payload(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {"value": value}
