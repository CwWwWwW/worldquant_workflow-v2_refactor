from __future__ import annotations

import atexit
import json
import logging
import os
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .repository import EventRepository
from .schema import initialize_schema
from .sqlite_store import connect_db
from .write_queue import QueueStats, SQLiteWriteQueue


VALID_STORAGE_MODES = {"hybrid", "sqlite_only", "jsonl_only"}
IO_DEGRADED_MODE = False
IO_DEGRADED_REASON = ""


@dataclass(slots=True)
class StorageConfig:
    mode: str = "hybrid"
    db_path: Path = Path("runtime/db/workflow.db")
    legacy_export: bool = True
    queue_batch_size: int = 100
    queue_flush_interval_seconds: float = 0.25
    health_check_interval_seconds: float = 60.0
    retention_days: int = 14


def set_io_degraded(value: bool, reason: str = "") -> None:
    global IO_DEGRADED_MODE, IO_DEGRADED_REASON
    IO_DEGRADED_MODE = bool(value)
    if reason:
        IO_DEGRADED_REASON = reason
    if value:
        logging.warning("[Storage] IO degraded mode enabled: %s", IO_DEGRADED_REASON or "unknown")


def is_io_degraded() -> bool:
    return IO_DEGRADED_MODE


class StorageManager:
    def __init__(self, config: StorageConfig | None = None, *, root: str | Path | None = None) -> None:
        from ..paths import ROOT

        self.root = Path(root or ROOT)
        self.config = config or load_storage_config(root=self.root)
        self._conn: sqlite3.Connection | None = None
        self._conn_lock = threading.Lock()
        self._queue: SQLiteWriteQueue | None = None
        self._queue_lock = threading.Lock()
        atexit.register(self.close)

    @property
    def mode(self) -> str:
        return self.config.mode

    @property
    def db_path(self) -> Path:
        return self.config.db_path

    def initialize(self) -> None:
        if self.mode == "jsonl_only":
            return
        with self._conn_lock:
            self._connection()
        self._ensure_queue()

    def write_event(self, path: str | Path, payload: dict[str, Any], *, max_bytes: int) -> bool:
        if self.mode == "jsonl_only":
            return False
        try:
            queue = self._ensure_queue()
            queue.put_event(
                path,
                payload,
                legacy_export=self.mode == "hybrid" and self.config.legacy_export,
                max_bytes=max_bytes,
            )
            return True
        except Exception as exc:
            set_io_degraded(True, str(exc))
            logging.info("SQLite event enqueue failed: %s", path, exc_info=True)
            return False

    def mirror_json_snapshot(self, path: str | Path, payload: Any) -> None:
        if self.mode == "jsonl_only":
            return
        try:
            self._ensure_queue().put_snapshot(path, payload)
        except Exception as exc:
            set_io_degraded(True, str(exc))
            logging.info("SQLite snapshot enqueue failed: %s", path, exc_info=True)

    def write_lineage_record(self, payload: dict[str, Any]) -> None:
        if self.mode == "jsonl_only":
            return
        try:
            self._ensure_queue().put_lineage(payload)
        except Exception as exc:
            set_io_degraded(True, str(exc))
            logging.info("SQLite lineage enqueue failed", exc_info=True)

    def write_candidate_record(self, payload: dict[str, Any]) -> None:
        if self.mode == "jsonl_only":
            return
        try:
            self._ensure_queue().put_candidate(payload)
        except Exception as exc:
            set_io_degraded(True, str(exc))
            logging.info("SQLite candidate enqueue failed", exc_info=True)

    def write_failure_record(self, payload: dict[str, Any]) -> None:
        if self.mode == "jsonl_only":
            return
        try:
            self._ensure_queue().put_failure(payload)
        except Exception as exc:
            set_io_degraded(True, str(exc))
            logging.info("SQLite failure enqueue failed", exc_info=True)

    def write_evolution_population_record(self, payload: dict[str, Any]) -> bool:
        if self.mode == "jsonl_only":
            return False
        try:
            self._ensure_queue().put_evolution_population(payload)
            return True
        except Exception as exc:
            set_io_degraded(True, str(exc))
            logging.info("SQLite evolution population enqueue failed", exc_info=True)
            return False

    def write_evolution_decision_record(self, payload: dict[str, Any]) -> bool:
        if self.mode == "jsonl_only":
            return False
        try:
            self._ensure_queue().put_evolution_decision(payload)
            return True
        except Exception as exc:
            set_io_degraded(True, str(exc))
            logging.info("SQLite evolution decision enqueue failed", exc_info=True)
            return False

    def write_evolution_policy_record(self, payload: dict[str, Any]) -> bool:
        if self.mode == "jsonl_only":
            return False
        try:
            self._ensure_queue().put_evolution_policy(payload)
            return True
        except Exception as exc:
            set_io_degraded(True, str(exc))
            logging.info("SQLite evolution policy enqueue failed", exc_info=True)
            return False

    def write_evolution_graph_record(self, payload: dict[str, Any]) -> bool:
        if self.mode == "jsonl_only":
            return False
        try:
            self._ensure_queue().put_evolution_graph(payload)
            return True
        except Exception as exc:
            set_io_degraded(True, str(exc))
            logging.info("SQLite evolution graph enqueue failed", exc_info=True)
            return False

    def write_lineage_value_record(self, payload: dict[str, Any]) -> bool:
        if self.mode == "jsonl_only":
            return False
        try:
            self._ensure_queue().put_lineage_value(payload)
            return True
        except Exception as exc:
            set_io_degraded(True, str(exc))
            logging.info("SQLite lineage value enqueue failed", exc_info=True)
            return False

    def write_simulator_observation_record(self, payload: dict[str, Any]) -> bool:
        if self.mode == "jsonl_only":
            return False
        try:
            self._ensure_queue().put_simulator_observation(payload)
            return True
        except Exception as exc:
            set_io_degraded(True, str(exc))
            logging.info("SQLite simulator observation enqueue failed", exc_info=True)
            return False

    def read_event_tail(self, path: str | Path, *, limit: int) -> list[dict[str, Any]]:
        if self.mode == "jsonl_only":
            return []
        try:
            conn = self._connection()
            return EventRepository(conn, root=self.root).tail_for_path(path, limit=limit)
        except Exception:
            logging.info("SQLite event tail read failed: %s", path, exc_info=True)
            return []

    def query_events(
        self,
        *,
        alpha_id: str = "",
        source: str = "",
        event_type: str = "",
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        if self.mode == "jsonl_only":
            return []
        try:
            conn = self._connection()
            return EventRepository(conn, root=self.root).query(
                alpha_id=alpha_id,
                source=source,
                event_type=event_type,
                limit=limit,
            )
        except Exception:
            logging.info("SQLite event query failed", exc_info=True)
            return []

    def flush(self, timeout: float | None = None) -> bool:
        queue = self._queue
        if queue is None:
            return True
        return queue.flush(timeout=timeout)

    def stats(self) -> QueueStats:
        queue = self._queue
        if queue is None:
            return QueueStats()
        return queue.stats()

    def close(self) -> None:
        queue = self._queue
        if queue is not None:
            queue.close()
            self._queue = None
        conn = self._conn
        if conn is not None:
            conn.close()
            self._conn = None

    def _connection(self) -> sqlite3.Connection:
        if self._conn is None:
            self.config.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = connect_db(self.config.db_path)
            initialize_schema(self._conn)
        return self._conn

    def _ensure_queue(self) -> SQLiteWriteQueue:
        if self.mode == "jsonl_only":
            raise RuntimeError("storage mode is jsonl_only")
        with self._queue_lock:
            if self._queue is None:
                self._queue = SQLiteWriteQueue(
                    self.config.db_path,
                    root=self.root,
                    batch_size=self.config.queue_batch_size,
                    flush_interval_seconds=self.config.queue_flush_interval_seconds,
                    degraded_callback=lambda enabled, reason: set_io_degraded(enabled, reason),
                )
            return self._queue


_MANAGER: StorageManager | None = None
_MANAGER_LOCK = threading.Lock()


def get_storage_manager() -> StorageManager:
    global _MANAGER
    with _MANAGER_LOCK:
        if _MANAGER is None:
            _MANAGER = StorageManager()
        return _MANAGER


def load_storage_config(*, root: str | Path | None = None) -> StorageConfig:
    from ..paths import CONFIG_FILE, ROOT, WORKFLOW_DB_FILE

    root_path = Path(root or ROOT)
    raw: dict[str, Any] = {}
    try:
        if CONFIG_FILE.exists():
            loaded = json.loads(CONFIG_FILE.read_text(encoding="utf-8-sig"))
            raw = loaded if isinstance(loaded, dict) else {}
    except Exception:
        raw = {}
    storage = raw.get("storage") if isinstance(raw.get("storage"), dict) else {}
    mode = str(os.getenv("WQ_STORAGE_MODE") or storage.get("mode") or "hybrid").strip().lower()
    if mode not in VALID_STORAGE_MODES:
        mode = "hybrid"
    db_value = os.getenv("WQ_STORAGE_DB_PATH") or storage.get("db_path") or str(WORKFLOW_DB_FILE)
    db_path = Path(str(db_value))
    if not db_path.is_absolute():
        db_path = root_path / db_path
    return StorageConfig(
        mode=mode,
        db_path=db_path,
        legacy_export=_as_bool(storage.get("legacy_export"), True),
        queue_batch_size=max(1, _as_int(storage.get("queue_batch_size"), 100)),
        queue_flush_interval_seconds=max(0.05, _as_float(storage.get("queue_flush_interval_seconds"), 0.25)),
        health_check_interval_seconds=max(5.0, _as_float(storage.get("health_check_interval_seconds"), 60.0)),
        retention_days=max(1, _as_int(storage.get("retention_days"), 14)),
    )


def _as_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
