from __future__ import annotations

import threading
from pathlib import Path


candidate_pool_lock = threading.RLock()
template_memory_lock = threading.RLock()
success_memory_lock = threading.RLock()
dashboard_snapshot_lock = threading.RLock()
evolution_memory_lock = threading.RLock()
failure_memory_lock = threading.RLock()
statistics_memory_lock = threading.RLock()
migration_memory_lock = threading.RLock()


def lock_for_memory_path(path: str | Path) -> threading.RLock:
    text = str(path).replace("\\", "/").lower()
    name = Path(path).name.lower()
    if name == "candidate_pool.json":
        return candidate_pool_lock
    if "dashboard_snapshot" in text or name.endswith(".snapshot.json"):
        return dashboard_snapshot_lock
    if name in {"migration_state.json", "migration_metrics.json"}:
        return migration_memory_lock
    if name == "operator_statistics.json":
        return statistics_memory_lock
    if "failure_patterns" in text or name == "failures.json":
        return failure_memory_lock
    if name == "alpha_lineage.json" or "memory/evolution" in text:
        return evolution_memory_lock
    return template_memory_lock

