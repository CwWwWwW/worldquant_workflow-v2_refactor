from __future__ import annotations

import json
import logging
import math
import os
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from utils.safe_json import safe_json_read, safe_json_write, safe_replace


DEFAULT_JSONL_MAX_BYTES = 25 * 1024 * 1024
DEFAULT_LOCK_TIMEOUT_SECONDS = 5.0


class FileLockTimeout(TimeoutError):
    pass


class FileLock:
    def __init__(
        self,
        path: Path,
        *,
        timeout_seconds: float = DEFAULT_LOCK_TIMEOUT_SECONDS,
        stale_seconds: float = 120.0,
    ) -> None:
        self.path = Path(path)
        self.timeout_seconds = timeout_seconds
        self.stale_seconds = stale_seconds
        self._fd: int | None = None

    def __enter__(self) -> "FileLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + self.timeout_seconds
        while True:
            try:
                self._fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_RDWR)
                os.write(self._fd, f"{os.getpid()} {datetime.now().isoformat(timespec='seconds')}\n".encode("utf-8"))
                return self
            except FileExistsError:
                self._remove_stale_lock()
                if time.monotonic() >= deadline:
                    raise FileLockTimeout(f"timed out waiting for lock: {self.path}")
                time.sleep(0.05)

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._fd is not None:
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None
        try:
            self.path.unlink()
        except OSError:
            pass

    def _remove_stale_lock(self) -> None:
        try:
            age = time.time() - self.path.stat().st_mtime
        except OSError:
            return
        if age <= self.stale_seconds:
            return
        try:
            self.path.unlink()
        except OSError:
            pass


@contextmanager
def file_lock(target: Path, *, timeout_seconds: float = DEFAULT_LOCK_TIMEOUT_SECONDS) -> Iterator[None]:
    lock_path = Path(target).with_name(f".{Path(target).name}.lock")
    with FileLock(lock_path, timeout_seconds=timeout_seconds):
        yield


def finite_float(value: Any, default: float = 0.0, *, minimum: float | None = None, maximum: float | None = None) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = float(default)
    if not math.isfinite(number):
        number = float(default)
    if minimum is not None:
        number = max(minimum, number)
    if maximum is not None:
        number = min(maximum, number)
    return number


def safe_json_value(value: Any) -> Any:
    if isinstance(value, float):
        return value if math.isfinite(value) else 0.0
    if isinstance(value, dict):
        return {str(key): safe_json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [safe_json_value(item) for item in value]
    if isinstance(value, tuple):
        return [safe_json_value(item) for item in value]
    return value


def safe_read_json(path: Path, default: Any) -> Any:
    path = Path(path)
    backup = path.with_suffix(path.suffix + ".bak")
    return safe_json_read(path, default, backup_path=backup, quarantine_corrupt=True)


def atomic_write_json(path: Path, payload: Any, *, make_backup: bool = True) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    cleaned = safe_json_value(payload)
    wrote = False
    try:
        with file_lock(path):
            if make_backup and path.exists():
                backup = path.with_suffix(path.suffix + ".bak")
                try:
                    with path.open("rb") as src, backup.open("wb") as dst:
                        dst.write(src.read())
                except OSError:
                    pass
            if not safe_json_write(path, cleaned):
                logging.warning("[AtomicWrite] skipped file=%s", path.name)
                return
            wrote = True
            if make_backup:
                try:
                    backup = path.with_suffix(path.suffix + ".bak")
                    with path.open("rb") as src, backup.open("wb") as dst:
                        dst.write(src.read())
                except OSError:
                    pass
    except Exception as exc:
        logging.warning("[MemoryLock] write_skipped file=%s error=%s", path.name, exc)
    if wrote:
        try:
            from .storage import get_storage_manager

            manager = get_storage_manager()
            if _is_within_root(path, manager.root):
                manager.mirror_json_snapshot(path, cleaned)
        except Exception:
            logging.info("[Storage] sqlite json mirror skipped file=%s", path.name, exc_info=True)


def append_jsonl(path: Path, payload: dict[str, Any], *, max_bytes: int = DEFAULT_JSONL_MAX_BYTES) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        from .storage import get_storage_manager

        manager = get_storage_manager()
        if _is_within_root(path, manager.root) and manager.write_event(path, safe_json_value(payload), max_bytes=max_bytes):
            try:
                manager.flush(timeout=1.0)
            except Exception:
                logging.info("[Storage] sqlite event flush skipped file=%s", path.name, exc_info=True)
            return
    except Exception:
        logging.info("[Storage] sqlite event write skipped file=%s", path.name, exc_info=True)
    _append_jsonl_legacy(path, payload, max_bytes=max_bytes)


def _append_jsonl_legacy(path: Path, payload: dict[str, Any], *, max_bytes: int = DEFAULT_JSONL_MAX_BYTES) -> None:
    with file_lock(path):
        rotate_if_large(path, max_bytes=max_bytes)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(safe_json_value(payload), ensure_ascii=False, allow_nan=False, default=str) + "\n")
            fh.flush()


def rotate_if_large(path: Path, *, max_bytes: int = DEFAULT_JSONL_MAX_BYTES) -> None:
    try:
        if path.stat().st_size <= max_bytes:
            return
    except OSError:
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive = path.with_name(f"{path.stem}.{stamp}{path.suffix}")
    safe_replace(path, archive)


def read_jsonl_tail(path: Path, *, limit: int, max_bytes: int = 256_000) -> list[dict[str, Any]]:
    path = Path(path)
    try:
        from .storage import get_storage_manager

        manager = get_storage_manager()
        if _is_within_root(path, manager.root):
            manager.flush(timeout=0.5)
            sqlite_rows = manager.read_event_tail(path, limit=limit)
            if sqlite_rows:
                return sqlite_rows[-limit:]
    except Exception:
        logging.info("[Storage] sqlite jsonl tail skipped file=%s", path.name, exc_info=True)
    try:
        with path.open("rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - max_bytes))
            text = fh.read().decode("utf-8-sig", errors="replace")
    except OSError:
        return []
    rows: list[dict[str, Any]] = []
    for line in text.splitlines()[-limit:]:
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def trim_old_files(directory: Path, pattern: str, *, keep: int) -> None:
    try:
        files = [path for path in Path(directory).glob(pattern) if path.is_file()]
    except OSError:
        return
    for path in sorted(files, key=lambda item: item.stat().st_mtime, reverse=True)[keep:]:
        try:
            path.unlink()
        except OSError:
            pass


def _quarantine_corrupt(path: Path) -> None:
    if not path.exists():
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = path.with_suffix(path.suffix + f".corrupt.{stamp}")
    safe_replace(path, target)


def _is_within_root(path: Path, root: Path) -> bool:
    try:
        resolved = Path(path).resolve()
        root_resolved = Path(root).resolve()
    except OSError:
        return False
    return resolved == root_resolved or root_resolved in resolved.parents
