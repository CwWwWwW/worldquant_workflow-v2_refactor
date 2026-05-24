from __future__ import annotations

import json
import logging
import math
import os
import queue
import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from utils.safe_json import safe_replace

from .repository import (
    CandidatePoolRepository,
    EventRepository,
    EvolutionMemoryRepository,
    FailurePatternRepository,
    LineageRepository,
    OperatorStatsRepository,
)
from .evolution_repository import EvolutionDBRepository
from .schema import initialize_schema
from .sqlite_store import connect_db


@dataclass(slots=True)
class QueueStats:
    backlog: int = 0
    failed_writes: int = 0
    sqlite_writes: int = 0
    legacy_writes: int = 0
    last_error: str = ""


class SQLiteWriteQueue:
    def __init__(
        self,
        db_path: str | Path,
        *,
        root: str | Path,
        batch_size: int = 100,
        flush_interval_seconds: float = 0.25,
        degraded_callback: Callable[[bool, str], None] | None = None,
    ) -> None:
        self.db_path = Path(db_path)
        self.root = Path(root)
        self.batch_size = max(1, int(batch_size))
        self.flush_interval_seconds = max(0.05, float(flush_interval_seconds))
        self.degraded_callback = degraded_callback
        self._queue: queue.Queue[dict[str, Any]] = queue.Queue()
        self._stop = threading.Event()
        self._started = threading.Event()
        self._thread = threading.Thread(target=self._run, name="wq-sqlite-write-queue", daemon=True)
        self._stats = QueueStats()
        self._stats_lock = threading.Lock()
        self._thread.start()
        self._started.wait(timeout=5.0)

    def put_event(self, path: str | Path, payload: dict[str, Any], *, legacy_export: bool, max_bytes: int) -> None:
        self._queue.put(
            {
                "kind": "event",
                "path": str(path),
                "payload": _clean(payload),
                "legacy_export": bool(legacy_export),
                "max_bytes": int(max_bytes),
            }
        )

    def put_snapshot(self, path: str | Path, payload: Any) -> None:
        self._queue.put({"kind": "snapshot", "path": str(path), "payload": _clean(payload)})

    def put_lineage(self, payload: dict[str, Any]) -> None:
        self._queue.put({"kind": "lineage", "payload": _clean(payload)})

    def put_candidate(self, payload: dict[str, Any]) -> None:
        self._queue.put({"kind": "candidate", "payload": _clean(payload)})

    def put_failure(self, payload: dict[str, Any]) -> None:
        self._queue.put({"kind": "failure", "payload": _clean(payload)})

    def put_evolution_population(self, payload: dict[str, Any]) -> None:
        self._queue.put({"kind": "evolution_population", "payload": _clean(payload)})

    def put_evolution_decision(self, payload: dict[str, Any]) -> None:
        self._queue.put({"kind": "evolution_decision", "payload": _clean(payload)})

    def put_evolution_policy(self, payload: dict[str, Any]) -> None:
        self._queue.put({"kind": "evolution_policy", "payload": _clean(payload)})

    def put_evolution_graph(self, payload: dict[str, Any]) -> None:
        self._queue.put({"kind": "evolution_graph", "payload": _clean(payload)})

    def put_lineage_value(self, payload: dict[str, Any]) -> None:
        self._queue.put({"kind": "lineage_value", "payload": _clean(payload)})

    def put_simulator_observation(self, payload: dict[str, Any]) -> None:
        self._queue.put({"kind": "simulator_observation", "payload": _clean(payload)})

    def flush(self, timeout: float | None = None) -> bool:
        deadline = None if timeout is None else time.monotonic() + max(0.0, timeout)
        while self._queue.unfinished_tasks:
            if deadline is not None and time.monotonic() >= deadline:
                return False
            time.sleep(0.02)
        return True

    def close(self, timeout: float = 2.0) -> None:
        self.flush(timeout=timeout)
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=timeout)

    def stats(self) -> QueueStats:
        with self._stats_lock:
            return QueueStats(
                backlog=self._queue.qsize(),
                failed_writes=self._stats.failed_writes,
                sqlite_writes=self._stats.sqlite_writes,
                legacy_writes=self._stats.legacy_writes,
                last_error=self._stats.last_error,
            )

    def _run(self) -> None:
        conn: sqlite3.Connection | None = None
        try:
            conn = connect_db(self.db_path)
            initialize_schema(conn)
            self._started.set()
            while not self._stop.is_set() or not self._queue.empty():
                batch = self._collect_batch()
                if not batch:
                    continue
                try:
                    self._write_batch(conn, batch)
                finally:
                    for _item in batch:
                        self._queue.task_done()
        except Exception as exc:
            self._record_failure(exc)
            self._set_degraded(True, str(exc))
            self._started.set()
            while not self._queue.empty():
                try:
                    self._queue.get_nowait()
                    self._queue.task_done()
                except queue.Empty:
                    break
        finally:
            if conn is not None:
                conn.close()

    def _collect_batch(self) -> list[dict[str, Any]]:
        try:
            first = self._queue.get(timeout=self.flush_interval_seconds)
        except queue.Empty:
            return []
        batch = [first]
        deadline = time.monotonic() + self.flush_interval_seconds
        while len(batch) < self.batch_size and time.monotonic() < deadline:
            try:
                batch.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return batch

    def _write_batch(self, conn: sqlite3.Connection, batch: list[dict[str, Any]]) -> None:
        last_error: Exception | None = None
        for attempt in range(5):
            try:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    self._write_sqlite(conn, batch)
                except Exception:
                    conn.execute("ROLLBACK")
                    raise
                else:
                    conn.execute("COMMIT")
                self._write_legacy(batch)
                with self._stats_lock:
                    self._stats.sqlite_writes += len(batch)
                return
            except sqlite3.OperationalError as exc:
                last_error = exc
                try:
                    conn.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
                if "locked" not in str(exc).lower() and "busy" not in str(exc).lower():
                    break
                time.sleep(0.2 * (attempt + 1))
            except Exception as exc:
                last_error = exc
                try:
                    conn.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
                break
        if last_error is not None:
            self._record_failure(last_error)
            self._set_degraded(True, str(last_error))

    def _write_sqlite(self, conn: sqlite3.Connection, batch: list[dict[str, Any]]) -> None:
        event_rows: list[tuple[str, dict[str, Any]]] = []
        for item in batch:
            kind = item.get("kind")
            payload = item.get("payload")
            if kind == "event" and isinstance(payload, dict):
                event_rows.append((str(item.get("path") or ""), payload))
            elif kind == "snapshot":
                _write_snapshot(conn, Path(str(item.get("path") or "")), payload)
            elif kind == "lineage" and isinstance(payload, dict):
                LineageRepository(conn).add_lineage(payload=payload)
            elif kind == "candidate" and isinstance(payload, dict):
                CandidatePoolRepository(conn).upsert_candidate(payload)
            elif kind == "failure" and isinstance(payload, dict):
                FailurePatternRepository(conn).insert_failure(payload)
            elif kind == "evolution_population" and isinstance(payload, dict):
                EvolutionDBRepository(conn).upsert_population_member(payload)
            elif kind == "evolution_decision" and isinstance(payload, dict):
                EvolutionDBRepository(conn).record_decision(payload)
            elif kind == "evolution_policy" and isinstance(payload, dict):
                EvolutionDBRepository(conn).upsert_policy_action(**payload)
            elif kind == "evolution_graph" and isinstance(payload, dict):
                EvolutionDBRepository(conn).upsert_graph_edge(
                    edge_type=str(payload.get("edge_type") or ""),
                    src=str(payload.get("src") or ""),
                    dst=str(payload.get("dst") or ""),
                    reward=_to_float(payload.get("reward", 0.0)),
                    success=bool(payload.get("success")),
                    payload=payload,
                )
            elif kind == "lineage_value" and isinstance(payload, dict):
                EvolutionDBRepository(conn).upsert_lineage_value(str(payload.get("alpha_id") or ""), payload)
            elif kind == "simulator_observation" and isinstance(payload, dict):
                EvolutionDBRepository(conn).record_simulator_observation(payload)
        if event_rows:
            EventRepository(conn, root=self.root).batch_insert_events(event_rows)

    def _write_legacy(self, batch: list[dict[str, Any]]) -> None:
        grouped: dict[tuple[str, int], list[dict[str, Any]]] = {}
        for item in batch:
            if item.get("kind") != "event" or not item.get("legacy_export"):
                continue
            payload = item.get("payload")
            if isinstance(payload, dict):
                grouped.setdefault((str(item.get("path") or ""), int(item.get("max_bytes") or 0)), []).append(payload)
        for (path_text, max_bytes), rows in grouped.items():
            path = Path(path_text)
            try:
                _append_jsonl_batch(path, rows, max_bytes=max_bytes)
                with self._stats_lock:
                    self._stats.legacy_writes += len(rows)
            except Exception as exc:
                logging.info("Legacy JSONL export failed: %s", path, exc_info=True)
                self._record_failure(exc)

    def _record_failure(self, exc: Exception) -> None:
        with self._stats_lock:
            self._stats.failed_writes += 1
            self._stats.last_error = str(exc)

    def _set_degraded(self, value: bool, reason: str) -> None:
        if self.degraded_callback is not None:
            self.degraded_callback(value, reason)


def _write_snapshot(conn: sqlite3.Connection, path: Path, payload: Any) -> None:
    name = path.name.lower()
    stem = path.stem
    if name == "candidate_pool.json" and isinstance(payload, list):
        CandidatePoolRepository(conn).replace_candidates([row for row in payload if isinstance(row, dict)])
        return
    if name == "operator_statistics.json" and isinstance(payload, dict):
        OperatorStatsRepository(conn).replace_from_mapping(payload)
        return
    if name == "failures.json" and isinstance(payload, list):
        FailurePatternRepository(conn).replace_failures([row for row in payload if isinstance(row, dict)])
        return
    repo = EvolutionMemoryRepository(conn)
    if name == "alpha_lineage.json" and isinstance(payload, list):
        repo.set_memory("snapshots", "alpha_lineage", payload)
        return
    if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
        repo.replace_namespace(stem, payload.get("data", {}))
        meta = {key: value for key, value in payload.items() if key != "data"}
        if meta:
            repo.set_memory("memory_meta", stem, meta)
        return
    repo.set_memory("snapshots", stem, payload)


def _append_jsonl_batch(path: Path, rows: list[dict[str, Any]], *, max_bytes: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _rotate_if_large(path, max_bytes=max_bytes)
    with path.open("a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(_clean(row), ensure_ascii=False, allow_nan=False, default=str) + "\n")


def _rotate_if_large(path: Path, *, max_bytes: int) -> None:
    if max_bytes <= 0:
        return
    try:
        if path.stat().st_size <= max_bytes:
            return
    except OSError:
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive = path.with_name(f"{path.stem}.{stamp}{path.suffix}")
    safe_replace(path, archive)


def _clean(value: Any) -> Any:
    if isinstance(value, float):
        return value if math.isfinite(value) else 0.0
    if isinstance(value, dict):
        return {str(key): _clean(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_clean(item) for item in value]
    if isinstance(value, tuple):
        return [_clean(item) for item in value]
    return value


def _to_float(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return number if math.isfinite(number) else 0.0
