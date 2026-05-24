from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from .sqlite_store import connect_db


@dataclass(slots=True)
class WalMaintenanceState:
    last_checkpoint_at: float = 0.0
    last_vacuum_at: float = 0.0


def checkpoint(db_path: str | Path, *, truncate: bool = True) -> list[tuple[int, int, int]]:
    conn = connect_db(db_path)
    try:
        pragma = "PRAGMA wal_checkpoint(TRUNCATE)" if truncate else "PRAGMA wal_checkpoint(PASSIVE)"
        return [tuple(row) for row in conn.execute(pragma).fetchall()]
    finally:
        conn.close()


def vacuum(db_path: str | Path) -> None:
    conn = connect_db(db_path)
    try:
        conn.execute("VACUUM")
    finally:
        conn.close()


def maybe_run_maintenance(
    db_path: str | Path,
    state: WalMaintenanceState,
    *,
    checkpoint_interval_seconds: float = 24 * 3600,
    vacuum_interval_seconds: float = 7 * 24 * 3600,
) -> WalMaintenanceState:
    now = time.time()
    if now - state.last_checkpoint_at >= checkpoint_interval_seconds:
        checkpoint(db_path, truncate=True)
        state.last_checkpoint_at = now
    if now - state.last_vacuum_at >= vacuum_interval_seconds:
        vacuum(db_path)
        state.last_vacuum_at = now
    return state
