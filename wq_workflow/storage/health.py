from __future__ import annotations

import os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from .manager import get_storage_manager, set_io_degraded


@dataclass(slots=True)
class StorageHealth:
    db_size: int = 0
    wal_size: int = 0
    queue_backlog: int = 0
    failed_writes: int = 0
    screenshot_count: int = 0
    html_count: int = 0
    trace_count: int = 0
    handle_count: int = 0
    degraded: bool = False
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def collect_health(
    *,
    root: str | Path | None = None,
    db_path: str | Path | None = None,
    max_wal_bytes: int = 512 * 1024 * 1024,
    max_queue_backlog: int = 10_000,
    max_failed_writes: int = 10,
    max_artifacts: int = 20_000,
) -> StorageHealth:
    from ..paths import ROOT, WORKFLOW_DB_FILE

    root_path = Path(root or ROOT)
    db = Path(db_path or WORKFLOW_DB_FILE)
    manager = get_storage_manager()
    stats = manager.stats()
    health = StorageHealth(
        db_size=_size(db),
        wal_size=_size(Path(str(db) + "-wal")),
        queue_backlog=stats.backlog,
        failed_writes=stats.failed_writes,
        screenshot_count=_count(root_path / "iterations", "*.png") + _count(root_path / "logs" / "failures", "*.png"),
        html_count=_count(root_path / "logs" / "failures", "*.html"),
        trace_count=_count(root_path / "logs" / "traces", "*.zip"),
        handle_count=_handle_count(),
    )
    artifact_count = health.screenshot_count + health.html_count + health.trace_count
    reasons: list[str] = []
    if health.wal_size > max_wal_bytes:
        reasons.append("wal_size")
    if health.queue_backlog > max_queue_backlog:
        reasons.append("queue_backlog")
    if health.failed_writes > max_failed_writes:
        reasons.append("failed_writes")
    if artifact_count > max_artifacts:
        reasons.append("artifact_count")
    if reasons:
        health.degraded = True
        health.reason = ",".join(reasons)
        set_io_degraded(True, health.reason)
    return health


def _size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _count(directory: Path, pattern: str) -> int:
    try:
        return sum(1 for path in directory.glob(pattern) if path.is_file())
    except OSError:
        return 0


def _handle_count() -> int:
    if os.name != "nt":
        return 0
    try:
        import subprocess

        output = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", f"(Get-Process -Id {os.getpid()}).HandleCount"],
            stderr=subprocess.DEVNULL,
        )
        return int(output.decode("utf-8", errors="ignore").strip() or "0")
    except Exception:
        return 0
