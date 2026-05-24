from __future__ import annotations

import json
import logging
import math
import os
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


REPLACE_BACKOFF_SECONDS = (0.2, 0.5, 1.0, 2.0, 3.0)


def safe_json_read(
    path: str | Path,
    default: Any = None,
    *,
    backup_path: str | Path | None = None,
    quarantine_corrupt: bool = False,
) -> Any:
    """Read UTF-8 JSON with short-lived file handles and safe fallbacks."""
    path = Path(path)
    try:
        with path.open("r", encoding="utf-8-sig") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return default
    except json.JSONDecodeError as exc:
        logging.warning("[AtomicWrite] json_corrupt file=%s error=%s", path.name, exc)
        if quarantine_corrupt:
            _quarantine_corrupt(path)
        if backup_path is not None:
            try:
                with Path(backup_path).open("r", encoding="utf-8-sig") as fh:
                    return json.load(fh)
            except (OSError, json.JSONDecodeError):
                return default
        return default
    except OSError as exc:
        logging.warning("[AtomicWrite] read_failed file=%s error=%s", path.name, exc)
        return default


def safe_json_write(path: str | Path, data: Any) -> bool:
    return atomic_write_json(path, data)


def atomic_write_json(path: str | Path, data: Any) -> bool:
    """Atomically write JSON via tmp file, flush, fsync, close, retry replace."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd: int | None = None
    temp_name = ""
    try:
        fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fd = None
            json.dump(_safe_json_value(data), fh, ensure_ascii=False, indent=2, allow_nan=False, default=str)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        if safe_replace(temp_name, path):
            return True
        _unlink_temp(temp_name)
        return False
    except Exception as exc:
        logging.warning("[AtomicWrite] write_failed file=%s error=%s", path.name, exc)
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        if temp_name:
            _unlink_temp(temp_name)
        return False


def safe_replace(
    src: str | Path,
    dst: str | Path,
    *,
    retry_delays: Iterable[float] = REPLACE_BACKOFF_SECONDS,
) -> bool:
    src = Path(src)
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    delays = tuple(retry_delays)
    attempts = max(len(delays), 1)
    last_error: Exception | None = None
    for index in range(attempts):
        try:
            os.replace(src, dst)
            return True
        except PermissionError as exc:
            last_error = exc
            logging.warning("[RetryReplace] retry=%s file=%s", index + 1, dst.name)
            if index < len(delays):
                time.sleep(delays[index])
        except OSError as exc:
            last_error = exc
            break
    logging.warning("[RetryReplace] failed file=%s error=%s", dst.name, last_error)
    return False


def _safe_json_value(value: Any) -> Any:
    if isinstance(value, float):
        return value if math.isfinite(value) else 0.0
    if isinstance(value, dict):
        return {str(key): _safe_json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_safe_json_value(item) for item in value]
    if isinstance(value, tuple):
        return [_safe_json_value(item) for item in value]
    return value


def _quarantine_corrupt(path: Path) -> None:
    if not path.exists():
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = path.with_suffix(path.suffix + f".corrupt.{stamp}")
    safe_replace(path, target)


def _unlink_temp(path: str | Path) -> None:
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        pass

