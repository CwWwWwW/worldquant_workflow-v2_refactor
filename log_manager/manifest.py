from __future__ import annotations

import hashlib
import json
import platform
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import ArchiveEntry, ManifestFileEntry
from utils.safe_json import atomic_write_json as safe_atomic_write_json, safe_json_read


MANIFEST_SCHEMA_VERSION = "log_manager_manifest_v1"
DEFAULT_CHUNK_SIZE = 4 * 1024 * 1024


def build_manifest(
    *,
    export_id: str,
    root: Path,
    filters: dict[str, Any],
    archive_format: str,
    files: list[ManifestFileEntry],
    archive_entries: list[ArchiveEntry] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "export_id": export_id,
        "export_timestamp": datetime.now().isoformat(timespec="seconds"),
        "root": str(root),
        "root_fingerprint": root_fingerprint(root),
        "workflow_version": _module_version(root / "wq_workflow" / "__init__.py"),
        "reward_version": _module_version(root / "wq_workflow" / "reward_engine.py"),
        "migration_version": _module_version(root / "wq_workflow" / "reward_migration" / "__init__.py"),
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "filters": filters,
        "archive_format": archive_format,
        "files": [entry.to_dict() for entry in files],
        "archive_entries": [entry.to_dict() for entry in archive_entries or []],
    }


def root_fingerprint(root: Path) -> str:
    parts = [
        str(root.resolve()),
        _safe_stat(root / "workflow.log"),
        _safe_stat(root / "logs" / "workflow_state.jsonl"),
        _safe_stat(root / "memory" / "evolution" / "candidate_pool.json"),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8", errors="replace")).hexdigest()


def sha256_file(path: Path, *, chunk_size: int = DEFAULT_CHUNK_SIZE) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def hash_and_count(path: Path, *, chunk_size: int = DEFAULT_CHUNK_SIZE) -> tuple[str, int]:
    digest = hashlib.sha256()
    line_count = 0
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(chunk_size), b""):
            digest.update(chunk)
            line_count += chunk.count(b"\n")
    return digest.hexdigest(), line_count


def load_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(path)
    sentinel = object()
    payload = safe_json_read(path, sentinel)
    if payload is sentinel or not isinstance(payload, dict):
        raise ValueError(f"invalid manifest json: {path}")
    return payload


def save_manifest(path: Path, manifest: dict[str, Any]) -> None:
    atomic_write_json(path, manifest)


def manifest_entries(manifest: dict[str, Any]) -> list[ManifestFileEntry]:
    return [ManifestFileEntry.from_dict(item) for item in manifest.get("files", []) if isinstance(item, dict)]


def atomic_write_json(path: Path, payload: Any) -> None:
    safe_atomic_write_json(path, payload)


def write_status(root: Path, **updates: Any) -> None:
    status_path = root / "logs" / "log_manager_status.json"
    try:
        current: dict[str, Any] = {}
        if status_path.exists():
            loaded = safe_json_read(status_path, {})
            if isinstance(loaded, dict):
                current = loaded
        current.update(updates)
        current.setdefault("progress", "idle")
        current.setdefault("archive_size", 0)
        current.setdefault("integrity_status", "unknown")
        current.setdefault("last_backup_time", "")
        current.setdefault("active_operation", "")
        current.setdefault("export_id", "")
        current.setdefault("message", "")
        atomic_write_json(status_path, current)
    except Exception:
        # Status is best-effort and must never affect the workflow.
        pass


def _module_version(path: Path) -> str:
    if not path.exists():
        return "missing"
    try:
        stat = path.stat()
        return f"mtime:{int(stat.st_mtime)}:sha256:{sha256_file(path)[:16]}"
    except OSError:
        return "unreadable"


def _safe_stat(path: Path) -> str:
    try:
        stat = path.stat()
        return f"{path.name}:{stat.st_size}:{int(stat.st_mtime)}"
    except OSError:
        return f"{path.name}:missing"
