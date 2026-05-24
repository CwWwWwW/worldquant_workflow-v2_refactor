from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from memory.file_locks import dashboard_snapshot_lock, lock_for_memory_path

from .paths import (
    ALPHA_LINEAGE_FILE,
    CANDIDATE_POOL_FILE,
    MIGRATION_METRICS_FILE,
    MIGRATION_STATE_FILE,
    SNAPSHOT_ALPHA_LINEAGE_FILE,
    SNAPSHOT_CANDIDATE_POOL_FILE,
    SNAPSHOT_MIGRATION_METRICS_FILE,
    SNAPSHOT_MIGRATION_STATE_FILE,
)
from .safe_io import atomic_write_json, safe_read_json


SNAPSHOT_INTERVAL_SECONDS = 2.0
_last_snapshot_at = 0.0

SNAPSHOT_PAIRS: tuple[tuple[Path, Path, Any], ...] = (
    (CANDIDATE_POOL_FILE, SNAPSHOT_CANDIDATE_POOL_FILE, []),
    (ALPHA_LINEAGE_FILE, SNAPSHOT_ALPHA_LINEAGE_FILE, []),
    (MIGRATION_STATE_FILE, SNAPSHOT_MIGRATION_STATE_FILE, {}),
    (MIGRATION_METRICS_FILE, SNAPSHOT_MIGRATION_METRICS_FILE, {}),
)


def maybe_refresh_dashboard_snapshot(*, force: bool = False) -> bool:
    global _last_snapshot_at
    now = time.monotonic()
    if not force and now - _last_snapshot_at < SNAPSHOT_INTERVAL_SECONDS:
        return False
    if refresh_dashboard_snapshot():
        _last_snapshot_at = now
        return True
    return False


def refresh_dashboard_snapshot() -> bool:
    ok = True
    with dashboard_snapshot_lock:
        for live_path, snapshot_path, default in SNAPSHOT_PAIRS:
            with lock_for_memory_path(live_path):
                payload = safe_read_json(live_path, default)
            with lock_for_memory_path(snapshot_path):
                try:
                    atomic_write_json(snapshot_path, payload, make_backup=False)
                    logging.info("[Snapshot] file=%s", snapshot_path.name)
                except Exception as exc:
                    logging.warning("[Snapshot] failed file=%s error=%s", snapshot_path.name, exc)
                    ok = False
    return ok

