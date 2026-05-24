from __future__ import annotations

import json
import os
import shutil
import tarfile
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from .manifest import load_manifest, manifest_entries, save_manifest, write_status
from .models import ImportRequest, ImportResult, ManifestFileEntry
from .replay import replay_logs
from utils.safe_json import atomic_write_json as safe_atomic_write_json, safe_json_read, safe_replace


PROGRESS_FILE = "import_progress.state"
LINE_SUFFIXES = {".log", ".jsonl", ".csv"}


def import_logs(
    source: str | Path,
    target_root: str | Path,
    mode: str = "offline",
    resume: bool = True,
    conflict_policy: str = "keep_existing",
) -> ImportResult:
    source_path = Path(source).resolve()
    target = Path(target_root).resolve()
    request = ImportRequest(str(source_path), str(target), mode, resume, conflict_policy)
    temp_dir: Path | None = None
    try:
        export_dir = _resolve_export_dir(source_path)
        if export_dir is None:
            temp_dir = Path(tempfile.mkdtemp(prefix="log_manager_import_"))
            export_dir = _extract_archive(source_path, temp_dir)
        manifest = load_manifest(export_dir / "manifest.json")
        export_id = str(manifest.get("export_id") or export_dir.name)
        progress_path = target / "log_imports" / export_id / PROGRESS_FILE
        _write_progress(progress_path, {"request": request.to_dict(), "phase": "starting", "completed_files": []})
        write_status(target, progress="starting", active_operation=f"import:{mode}", export_id=export_id)
        if mode == "offline":
            result = _offline_import(export_dir, target, manifest)
        elif mode == "replay":
            result = _replay_import(export_dir, target, manifest)
        elif mode == "incremental":
            if _workflow_running(target):
                result = ImportResult("incremental", str(target), errors=["workflow is running; incremental import refused"])
                _write_progress(progress_path, {"request": request.to_dict(), "phase": "refused", "completed_files": []})
                write_status(target, progress="refused", active_operation="", export_id=export_id, message="workflow is running")
                return result
            result = _incremental_import(export_dir, target, manifest, conflict_policy, progress_path)
        elif mode == "restore":
            result = _restore_import(export_dir, target, manifest, progress_path)
        else:
            raise ValueError("mode must be offline, replay, incremental, or restore")
        _write_progress(progress_path, {"request": request.to_dict(), "phase": "completed", "completed_files": result.imported_files})
        write_status(target, progress="completed", active_operation="", export_id=export_id, message=f"import {mode} completed")
        return result
    finally:
        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)


def _offline_import(export_dir: Path, target: Path, manifest: dict[str, Any]) -> ImportResult:
    export_id = str(manifest.get("export_id") or export_dir.name)
    target_dir = target / "log_imports" / export_id
    imported: list[str] = []
    if target_dir.exists():
        shutil.rmtree(target_dir)
    shutil.copytree(export_dir, target_dir)
    for entry in manifest_entries(manifest):
        if entry.source_exists:
            imported.append(entry.relative_path)
    return ImportResult("offline", str(target_dir), imported_files=imported)


def _replay_import(export_dir: Path, target: Path, manifest: dict[str, Any]) -> ImportResult:
    export_id = str(manifest.get("export_id") or export_dir.name)
    target_dir = target / "log_imports" / export_id
    target_dir.mkdir(parents=True, exist_ok=True)
    output_path = target_dir / "replay_events.jsonl"
    replay_logs(export_dir, output_path=output_path)
    return ImportResult("replay", str(target_dir), imported_files=[str(output_path)])


def _incremental_import(
    export_dir: Path,
    target: Path,
    manifest: dict[str, Any],
    conflict_policy: str,
    progress_path: Path,
) -> ImportResult:
    imported: list[str] = []
    skipped: list[str] = []
    warnings: list[str] = []
    export_id = str(manifest.get("export_id") or export_dir.name)
    conflict_dir = target / "log_imports" / export_id / "conflicts"
    for entry in manifest_entries(manifest):
        if not entry.source_exists:
            skipped.append(entry.relative_path)
            continue
        src = export_dir / "files" / entry.relative_path
        dst = target / entry.relative_path
        _write_progress(progress_path, {"phase": "incremental", "current_file": entry.relative_path, "completed_files": imported})
        if dst.suffix.lower() in LINE_SUFFIXES:
            changed = _append_incremental(src, dst)
        elif dst.suffix.lower() == ".json":
            changed = _merge_json(src, dst, conflict_dir, conflict_policy, warnings)
        else:
            changed = _copy_if_missing(src, dst)
        if changed:
            imported.append(entry.relative_path)
        else:
            skipped.append(entry.relative_path)
    return ImportResult("incremental", str(target), imported, skipped, warnings)


def _restore_import(export_dir: Path, target: Path, manifest: dict[str, Any], progress_path: Path) -> ImportResult:
    if _workflow_running(target):
        return ImportResult("restore", str(target), errors=["workflow is running; restore refused"])
    export_id = str(manifest.get("export_id") or export_dir.name)
    backup_dir = target / "log_imports" / "backups" / export_id
    staging = target / "log_imports" / export_id / "restore_staging"
    if staging.exists():
        shutil.rmtree(staging)
    imported: list[str] = []
    for entry in manifest_entries(manifest):
        if not entry.source_exists:
            continue
        src = export_dir / "files" / entry.relative_path
        staged = staging / entry.relative_path
        staged.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, staged)
    for entry in manifest_entries(manifest):
        if not entry.source_exists:
            continue
        rel = entry.relative_path
        dst = target / rel
        staged = staging / rel
        _write_progress(progress_path, {"phase": "restore", "current_file": rel, "completed_files": imported})
        if dst.exists():
            backup = backup_dir / rel
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dst, backup)
        dst.parent.mkdir(parents=True, exist_ok=True)
        safe_replace(staged, dst)
        imported.append(rel)
    shutil.rmtree(staging, ignore_errors=True)
    return ImportResult("restore", str(target), imported_files=imported)


def _append_incremental(src: Path, dst: Path) -> bool:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if not dst.exists():
        shutil.copy2(src, dst)
        return True
    src_size = src.stat().st_size
    dst_size = dst.stat().st_size
    if src_size <= dst_size:
        return False
    if not _prefix_matches(src, dst, dst_size):
        return False
    with src.open("rb") as in_fh, dst.open("ab") as out_fh:
        in_fh.seek(dst_size)
        shutil.copyfileobj(in_fh, out_fh, length=4 * 1024 * 1024)
    return True


def _merge_json(src: Path, dst: Path, conflict_dir: Path, conflict_policy: str, warnings: list[str]) -> bool:
    if not dst.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        return True
    try:
        incoming = safe_json_read(src, None)
        existing = safe_json_read(dst, None)
    except OSError as exc:
        warnings.append(f"json merge skipped for {dst.name}: {exc}")
        _save_conflict(src, conflict_dir / dst.name)
        return False
    if incoming is None or existing is None:
        warnings.append(f"json merge skipped for {dst.name}: invalid json")
        _save_conflict(src, conflict_dir / dst.name)
        return False
    if isinstance(incoming, list) and isinstance(existing, list):
        merged = _merge_json_lists(existing, incoming)
        if len(merged) == len(existing):
            return False
        _atomic_json(dst, merged)
        return True
    if conflict_policy == "overwrite":
        shutil.copy2(src, dst)
        return True
    _save_conflict(src, conflict_dir / dst.name)
    return False


def _merge_json_lists(existing: list[Any], incoming: list[Any]) -> list[Any]:
    result = list(existing)
    seen = {_identity(item) for item in existing}
    for item in incoming:
        identity = _identity(item)
        if identity in seen:
            continue
        result.append(item)
        seen.add(identity)
    return result


def _identity(value: Any) -> str:
    if isinstance(value, dict):
        if value.get("id"):
            return str(value.get("id"))
        for keys in [("alpha_id", "timestamp"), ("alpha_id", "fingerprint"), ("parent_id", "alpha_id")]:
            if all(value.get(key) for key in keys):
                return "|".join(str(value.get(key)) for key in keys)
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _copy_if_missing(src: Path, dst: Path) -> bool:
    if dst.exists():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return True


def _prefix_matches(src: Path, dst: Path, length: int) -> bool:
    remaining = length
    with src.open("rb") as left, dst.open("rb") as right:
        while remaining > 0:
            chunk_size = min(4 * 1024 * 1024, remaining)
            if left.read(chunk_size) != right.read(chunk_size):
                return False
            remaining -= chunk_size
    return True


def _workflow_running(root: Path) -> bool:
    pid_file = root / "logs" / "workflow_active.pid"
    try:
        with pid_file.open("r", encoding="utf-8-sig") as fh:
            pid_text = fh.read().strip()
        pid = int(pid_text)
    except (OSError, ValueError):
        return False
    if pid <= 0:
        return False
    if pid == os.getpid():
        return True
    if os.name == "nt":
        try:
            import subprocess

            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            output = result.stdout.decode("utf-8", errors="replace") + result.stderr.decode("utf-8", errors="replace")
            return str(pid) in output
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _resolve_export_dir(source: Path) -> Path | None:
    if source.is_dir():
        if (source / "manifest.json").exists():
            return source
        candidates = [path for path in source.iterdir() if path.is_dir() and (path / "manifest.json").exists()]
        if candidates:
            return sorted(candidates, key=lambda path: path.stat().st_mtime, reverse=True)[0]
    return None


def _extract_archive(source: Path, temp_dir: Path) -> Path:
    archive = _recombine_if_part(source, temp_dir)
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as zf:
            _safe_extract_zip(zf, temp_dir)
    elif tarfile.is_tarfile(archive):
        with tarfile.open(archive) as tf:
            _safe_extract_tar(tf, temp_dir)
    else:
        raise ValueError(f"unsupported archive: {source}")
    resolved = _resolve_export_dir(temp_dir)
    if resolved is None:
        raise FileNotFoundError("manifest not found in archive")
    return resolved


def _recombine_if_part(source: Path, temp_dir: Path) -> Path:
    if ".part" not in source.name:
        return source
    prefix = source.name.split(".part", 1)[0]
    parts = sorted(source.parent.glob(f"{prefix}.part*"))
    combined = temp_dir / prefix
    with combined.open("wb") as dst:
        for part in parts:
            with part.open("rb") as src:
                shutil.copyfileobj(src, dst, length=4 * 1024 * 1024)
    return combined


def _save_conflict(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def _atomic_json(path: Path, payload: Any) -> None:
    safe_atomic_write_json(path, payload)


def _write_progress(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload.setdefault("updated_at", datetime.now().isoformat(timespec="seconds"))
    safe_atomic_write_json(path, payload)


def _safe_extract_zip(zf: zipfile.ZipFile, target: Path) -> None:
    target_root = target.resolve()
    for member in zf.infolist():
        destination = (target / member.filename).resolve()
        if target_root not in [destination, *destination.parents]:
            raise ValueError(f"unsafe archive path: {member.filename}")
    zf.extractall(target)


def _safe_extract_tar(tf: tarfile.TarFile, target: Path) -> None:
    target_root = target.resolve()
    for member in tf.getmembers():
        destination = (target / member.name).resolve()
        if target_root not in [destination, *destination.parents]:
            raise ValueError(f"unsafe archive path: {member.name}")
    tf.extractall(target)
