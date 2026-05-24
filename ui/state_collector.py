from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from wq_workflow.paths import (
    ITERATION_LOG_FILE,
    ROOT,
    STATE_LOG_FILE,
)
from wq_workflow.safe_io import atomic_write_json, finite_float, safe_read_json

from .log_stream import LogStreamer
from .metrics import pass_rate_from_rows, population_metrics, queue_size_from_workers
from .models import DashboardSnapshot, LogManagerStatus, MigrationMetrics, WorkerState, WorkflowStatus


STATE_CACHE_FILE = ROOT / "state_cache.json"
UI_LOG_DIR = ROOT / "ui_logs"
UI_DASHBOARD_LOG = UI_LOG_DIR / "dashboard.log"
PID_FILE = ROOT / "logs" / "workflow_active.pid"
LOG_MANAGER_STATUS_FILE = ROOT / "logs" / "log_manager_status.json"
PROCESS_RUNNING_CACHE_TTL_SECONDS = 5.0
WORKER_TTL_SECONDS = 180
WORKER_STALE_SECONDS = 180
WORKFLOW_STALLED_SECONDS = 1_800
MIGRATION_STALE_SECONDS = 300
MAX_EVENT_AGE_SECONDS = 86_400
_PROCESS_RUNNING_CACHE: dict[int, tuple[float, bool]] = {}

ACTIVE_WORKER_EVENTS = {
    "STATE_ENTER",
    "STATE_UPDATE",
    "STATE_PROGRESS",
    "STATE_RETRY",
    "STATE_HEARTBEAT",
    "STATE_TIMEOUT",
    "STATE_FATAL",
}

STATE_TIMEOUTS = {
    "INIT": 20,
    "AUTH_CHECK": 180,
    "OPEN_SIMULATE": 150,
    "EDITOR_READY": 240,
    "WRITE_CODE": 150,
    "WRITE_NAME": 120,
    "CLICK_RUN": 90,
    "WAIT_QUEUE": 180,
    "WAIT_RESULT": 1_200,
    "PARSE_RESULT": 120,
    "QUALITY_CHECK": 90,
    "ADD_FAVORITE": 180,
    "FINISHED": 60,
}


class StateCollector:
    def __init__(self, *, root: Path = ROOT, cache_path: Path = STATE_CACHE_FILE) -> None:
        self.root = root
        self.cache_path = cache_path
        self.log_streamer = LogStreamer()
        self.last_snapshot: DashboardSnapshot | None = None
        self.snapshot_dir = self.root / "memory" / "dashboard_snapshot"

    def collect(self, *, log_filter: str = "") -> DashboardSnapshot:
        errors: list[str] = []
        pool_rows = _read_json_list(self._snapshot_path("candidate_pool"), errors)
        lineage_rows = _read_json_list(self._snapshot_path("alpha_lineage"), errors)
        workers = self._collect_workers(errors)
        migration = self._collect_migration(errors, workers=workers)
        population = population_metrics(pool_rows, lineage_rows)
        workflow = self._collect_workflow(
            workers=workers,
            population_count=population.count,
            pass_rate=pass_rate_from_rows(pool_rows, lineage_rows),
            migration_state=migration.state,
            reward_mode="HYBRID_V2" if migration.v2_weight > 0 else "LEGACY",
            errors=errors,
            pool_rows=pool_rows,
        )
        logs = self.log_streamer.poll(filter_text=log_filter)[-200:]
        last_success = self._last_success(pool_rows)
        snapshot = DashboardSnapshot(
            updated_at=datetime.now().isoformat(timespec="seconds"),
            workflow=workflow,
            workers=workers,
            population=population,
            migration=migration,
            logs=logs,
            log_manager=self._collect_log_manager(errors),
            last_success=last_success,
            source_mtimes=self._source_mtimes(),
            stale=bool(errors),
            errors=errors[-5:],
        )
        self._write_cache(snapshot)
        self.last_snapshot = snapshot
        return snapshot

    def _snapshot_path(self, name: str) -> Path:
        return self.snapshot_dir / f"{name}.snapshot.json"

    def _collect_workers(self, errors: list[str]) -> list[WorkerState]:
        pid = _read_pid(errors)
        if not (pid and _process_running(pid)):
            return []
        events = _read_jsonl_tail(STATE_LOG_FILE, limit=2_000, errors=errors)
        active: dict[str, dict[str, Any]] = {}
        restarts: dict[str, int] = {}
        now = time.time()
        for event in events:
            alpha_id = str(event.get("alpha_id") or "unknown")
            event_name = str(event.get("event") or "")
            state = str(event.get("state") or "")
            event_time = str(event.get("time") or "")
            event_ts = _parse_time(event_time) or now
            if now - event_ts > MAX_EVENT_AGE_SECONDS:
                continue
            if "RESTART" in state.upper() or "RESTART" in str(event.get("recovery") or "").upper():
                restarts[alpha_id] = restarts.get(alpha_id, 0) + 1
            if event_name == "STATE_ENTER":
                active[alpha_id] = {
                    "state": state,
                    "started_at": event_ts,
                    "last_event_at": event_ts,
                    "last_event_text": event_time,
                    "last_seen": event_ts,
                    "fatal": False,
                }
            elif event_name == "STATE_EXIT":
                if active.get(alpha_id, {}).get("state") == state:
                    active.pop(alpha_id, None)
                elif alpha_id in active:
                    active[alpha_id]["last_event_at"] = event_ts
                    active[alpha_id]["last_event_text"] = event_time
            elif event_name in {"STATE_FATAL", "STATE_TIMEOUT"}:
                active[alpha_id] = {
                    "state": state or "FATAL_ERROR",
                    "started_at": event_ts,
                    "last_event_at": event_ts,
                    "last_event_text": event_time,
                    "last_seen": event_ts,
                    "fatal": event_name == "STATE_FATAL",
                }
            elif event_name in ACTIVE_WORKER_EVENTS or alpha_id in active:
                worker = active.setdefault(
                    alpha_id,
                    {
                        "state": state or "UNKNOWN",
                        "started_at": event_ts,
                        "last_event_at": event_ts,
                        "last_event_text": event_time,
                        "last_seen": event_ts,
                        "fatal": False,
                    },
                )
                if state:
                    worker["state"] = state
                worker["last_event_at"] = event_ts
                worker["last_event_text"] = event_time
                worker["last_seen"] = event_ts
        active = {
            alpha_id: data
            for alpha_id, data in active.items()
            if now - _float(data.get("last_seen"), 0.0) < WORKER_TTL_SECONDS
        }
        workers: list[WorkerState] = []
        for index, (alpha_id, data) in enumerate(sorted(active.items()), start=1):
            state = str(data.get("state") or "UNKNOWN")
            started_at = float(data.get("started_at") or now)
            last_event_at = float(data.get("last_event_at") or started_at)
            runtime = max(0.0, now - started_at)
            idle_for = max(0.0, now - last_event_at)
            timeout = STATE_TIMEOUTS.get(state, WORKFLOW_STALLED_SECONDS)
            if data.get("fatal"):
                health = "FATAL"
            elif "RESTART" in state.upper():
                health = "RESTARTING"
            elif runtime > timeout or idle_for > WORKER_STALE_SECONDS:
                health = "STALLED"
            else:
                health = "RUNNING"
            workers.append(
                WorkerState(
                    worker_id=f"BW-{index}",
                    alpha_id=alpha_id,
                    current_task=state,
                    runtime_seconds=round(runtime, 1),
                    restart_count=restarts.get(alpha_id, 0),
                    health=health,
                    current_alpha=alpha_id,
                    last_event_at=str(data.get("last_event_text") or ""),
                )
            )
        return workers

    def _collect_migration(self, errors: list[str], *, workers: list[WorkerState] | None = None) -> MigrationMetrics:
        state_file = self._snapshot_path("migration_state")
        metrics_file = self._snapshot_path("migration_metrics")
        metrics_mtime: float | None = None
        try:
            metrics_mtime = metrics_file.stat().st_mtime
        except OSError:
            metrics_mtime = None
        if metrics_mtime is not None:
            now = time.time()
            if now - metrics_mtime > MIGRATION_STALE_SECONDS:
                return MigrationMetrics()
            pid = _read_pid(errors)
            workflow_start = _pid_mtime() if pid and _process_running(pid) else None
            if workflow_start and metrics_mtime < workflow_start:
                return MigrationMetrics()
        state_payload = _read_json_dict(state_file, errors, missing_ok=True)
        metrics_payload = _read_json_dict(metrics_file, errors, missing_ok=True)
        state_block = metrics_payload.get("state") if isinstance(metrics_payload.get("state"), dict) else state_payload
        population = metrics_payload.get("population_health") if isinstance(metrics_payload.get("population_health"), dict) else {}
        stability = metrics_payload.get("stability") if isinstance(metrics_payload.get("stability"), dict) else {}
        state = str(metrics_payload.get("current_state") or state_block.get("state") or "shadow")
        legacy_weight = _float(metrics_payload.get("legacy_weight", state_block.get("legacy_weight")), 1.0)
        v2_weight = _float(metrics_payload.get("v2_weight", state_block.get("v2_weight")), 0.0)
        diversity = _float(population.get("diversity_index"), 0.0)
        correlation = _float(population.get("average_correlation"), 0.0)
        return MigrationMetrics(
            state=state,
            legacy_weight=legacy_weight,
            v2_weight=v2_weight,
            rollback_count=_int(metrics_payload.get("rollback_count", state_block.get("rollback_count")), 0),
            reward_variance=_float(metrics_payload.get("reward_variance", stability.get("reward_variance")), 0.0),
            diversity_stability=round(max(0.0, min(1.0, diversity * (1.0 - correlation))), 6),
            updated_at=str(metrics_payload.get("timestamp") or state_block.get("last_transition_at") or ""),
        )

    def _collect_workflow(
        self,
        *,
        workers: list[WorkerState],
        population_count: int,
        pass_rate: float,
        migration_state: str,
        reward_mode: str,
        errors: list[str],
        pool_rows: list[dict[str, Any]],
    ) -> WorkflowStatus:
        pid = _read_pid(errors)
        running = bool(pid and _process_running(pid))
        start_time = _pid_mtime() if running else None
        runtime = max(0.0, time.time() - start_time) if start_time else 0.0
        if any(worker.health == "FATAL" for worker in workers):
            status = "ERROR"
        elif any(worker.health == "STALLED" for worker in workers):
            status = "STALLED"
        elif running:
            status = "RUNNING"
        else:
            status = "IDLE"
        last_success = self._last_success(pool_rows)
        return WorkflowStatus(
            status=status,
            population_count=population_count,
            queue_size=queue_size_from_workers(workers),
            pass_rate=pass_rate,
            reward_mode=reward_mode,
            migration_state=migration_state,
            runtime_seconds=round(runtime, 1),
            last_success_time=str(last_success.get("timestamp") or ""),
            pid=pid,
        )

    def _last_success(self, pool_rows: list[dict[str, Any]]) -> dict[str, Any]:
        successful = [row for row in pool_rows if row.get("passed") or row.get("template_success")]
        if not successful:
            return {}
        successful.sort(key=lambda row: str(row.get("timestamp") or ""))
        row = successful[-1]
        return {
            "alpha_id": row.get("alpha_id", ""),
            "timestamp": row.get("timestamp", ""),
            "template_success": bool(row.get("template_success")),
        }

    def _source_mtimes(self) -> dict[str, float]:
        paths = [
            PID_FILE,
            STATE_LOG_FILE,
            self._snapshot_path("candidate_pool"),
            self._snapshot_path("alpha_lineage"),
            self._snapshot_path("migration_state"),
            self._snapshot_path("migration_metrics"),
            ITERATION_LOG_FILE,
            self.root / "logs" / "log_manager_status.json",
        ]
        result: dict[str, float] = {}
        for path in paths:
            try:
                result[str(path)] = path.stat().st_mtime
            except OSError:
                continue
        return result

    def _collect_log_manager(self, errors: list[str]) -> LogManagerStatus:
        status_file = self.root / "logs" / "log_manager_status.json"
        if not status_file.exists():
            return LogManagerStatus()
        payload = safe_read_json(status_file, {})
        if not isinstance(payload, dict):
            errors.append("log_manager_status_invalid")
            return LogManagerStatus()
        return LogManagerStatus(
            progress=str(payload.get("progress") or "idle"),
            archive_size=_int(payload.get("archive_size"), 0),
            integrity_status=str(payload.get("integrity_status") or "unknown"),
            last_backup_time=str(payload.get("last_backup_time") or ""),
            active_operation=str(payload.get("active_operation") or ""),
            export_id=str(payload.get("export_id") or ""),
            message=str(payload.get("message") or ""),
        )

    def _write_cache(self, snapshot: DashboardSnapshot) -> None:
        payload = snapshot.to_dict()
        try:
            atomic_write_json(self.cache_path, payload, make_backup=False)
        except Exception as exc:
            log_dashboard_error(f"cache_write_failed: {exc}")


def log_dashboard_error(message: str) -> None:
    try:
        UI_LOG_DIR.mkdir(parents=True, exist_ok=True)
        with UI_DASHBOARD_LOG.open("a", encoding="utf-8") as fh:
            fh.write(f"{datetime.now().isoformat(timespec='seconds')} {message}\n")
    except OSError:
        pass


def _read_pid(errors: list[str]) -> int | None:
    try:
        with PID_FILE.open("r", encoding="utf-8-sig") as fh:
            text = fh.read().strip()
        return int(text) if text else None
    except FileNotFoundError:
        return None
    except Exception as exc:
        errors.append(f"pid_read_failed:{exc}")
        return None


def _pid_mtime() -> float | None:
    try:
        return PID_FILE.stat().st_mtime
    except OSError:
        return None


def _process_running(pid: int) -> bool:
    if pid <= 0:
        return False
    cached = _PROCESS_RUNNING_CACHE.get(pid)
    now = time.monotonic()
    if cached and now - cached[0] <= PROCESS_RUNNING_CACHE_TTL_SECONDS:
        return cached[1]
    if os.name == "nt":
        try:
            import subprocess

            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            output = result.stdout.decode("utf-8", errors="ignore") + result.stderr.decode("utf-8", errors="ignore")
            running = str(pid) in output
            _PROCESS_RUNNING_CACHE[pid] = (now, running)
            return running
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        _PROCESS_RUNNING_CACHE[pid] = (now, True)
        return True
    except OSError:
        _PROCESS_RUNNING_CACHE[pid] = (now, False)
        return False


def _read_json_list(path: Path, errors: list[str]) -> list[dict[str, Any]]:
    if not path.exists():
        log_dashboard_error(f"[Snapshot] missing: {path.name}")
        return []
    sentinel = object()
    data = safe_read_json(path, sentinel)
    if data is sentinel:
        errors.append(f"snapshot_read_failed:{path.name}")
        log_dashboard_error(f"[Snapshot] read_failed: {path.name}")
        return []
    if not isinstance(data, list):
        errors.append(f"snapshot_invalid:{path.name}")
        log_dashboard_error(f"[Snapshot] invalid: {path.name}")
        return []
    return data


def _read_json_dict(path: Path, errors: list[str], *, missing_ok: bool = False) -> dict[str, Any]:
    if not path.exists():
        if not missing_ok:
            errors.append(f"snapshot_missing:{path.name}")
        log_dashboard_error(f"[Snapshot] missing: {path.name}")
        return {}
    sentinel = object()
    data = safe_read_json(path, sentinel)
    if data is sentinel:
        errors.append(f"snapshot_read_failed:{path.name}")
        log_dashboard_error(f"[Snapshot] read_failed: {path.name}")
        return {}
    if not isinstance(data, dict):
        errors.append(f"snapshot_invalid:{path.name}")
        log_dashboard_error(f"[Snapshot] invalid: {path.name}")
        return {}
    return data


def _read_jsonl_tail(path: Path, *, limit: int, errors: list[str]) -> list[dict[str, Any]]:
    try:
        from wq_workflow.storage import get_storage_manager

        manager = get_storage_manager()
        manager.flush(timeout=0.5)
        rows = manager.read_event_tail(path, limit=limit)
        if rows:
            return rows[-limit:]
    except Exception:
        pass
    try:
        with path.open("rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - 256_000))
            text = fh.read().decode("utf-8", errors="ignore")
    except FileNotFoundError:
        return []
    except OSError as exc:
        errors.append(f"jsonl_read_failed:{path.name}:{exc}")
        return []
    rows: list[dict[str, Any]] = []
    for line in text.splitlines()[-limit:]:
        try:
            line = line.lstrip("\ufeff")
            value = json.loads(line)
        except Exception:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def _parse_time(value: str) -> float | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value[:19], fmt).timestamp()
        except ValueError:
            continue
    return None


def _float(value: Any, default: float = 0.0) -> float:
    return finite_float(value, default)


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
