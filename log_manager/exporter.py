from __future__ import annotations

import csv
import io
import json
import os
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from .archive import archive_logs
from .manifest import (
    build_manifest,
    hash_and_count,
    save_manifest,
    write_status,
)
from .models import ExportRequest, ExportResult, LogFileSpec, ManifestFileEntry
from .parsers.log_parser import parse_log_line
from utils.safe_json import atomic_write_json as safe_atomic_write_json, safe_json_read, safe_replace
from wq_workflow.storage.replay_index import export_memory_snapshot


LINE_SUFFIXES = {".log", ".jsonl", ".csv"}
JSON_SUFFIXES = {".json"}
EXPORT_FILE_DIR = "files"
PROGRESS_FILE = "export_progress.state"


def export_logs(
    root: str | Path,
    output_dir: str | Path,
    since: str | datetime | None = None,
    until: str | datetime | None = None,
    task_id: str | None = None,
    alpha_id: str | None = None,
    worker_id: str | None = None,
    archive_format: str = "zip",
    resume: bool = True,
) -> ExportResult:
    root_path = Path(root).resolve()
    output_root = Path(output_dir).resolve()
    filters = {
        "since": _time_text(since),
        "until": _time_text(until),
        "task_id": task_id,
        "alpha_id": alpha_id,
        "worker_id": worker_id,
    }
    export_id = _existing_export_id(output_root) if resume else ""
    if not export_id:
        export_id = f"log_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    export_dir = output_root / export_id
    files_dir = export_dir / EXPORT_FILE_DIR
    files_dir.mkdir(parents=True, exist_ok=True)
    progress_path = export_dir / PROGRESS_FILE
    progress = _load_progress(progress_path) if resume else {}
    completed = set(progress.get("completed_files") or [])
    warnings: list[str] = []
    entries: list[ManifestFileEntry] = []

    request = ExportRequest(
        root=str(root_path),
        output_dir=str(output_root),
        since=filters["since"],
        until=filters["until"],
        task_id=task_id,
        alpha_id=alpha_id,
        worker_id=worker_id,
        archive_format=archive_format,
        resume=resume,
    )
    _write_progress(
        progress_path,
        {
            "export_id": export_id,
            "request": request.to_dict(),
            "completed_files": sorted(completed),
            "current_file": "",
            "source_offset": 0,
        },
    )
    write_status(
        root_path,
        progress="starting",
        active_operation="export",
        export_id=export_id,
        message="log export starting",
    )

    specs = discover_log_files(root_path)
    total_specs = len(specs)
    for spec in specs:
        rel = spec.relative_path
        src = root_path / rel
        dst = files_dir / rel
        if rel in completed and dst.exists():
            entry = _entry_from_exported(dst, src, spec)
            entries.append(entry)
            continue
        _write_progress(
            progress_path,
            {
                "export_id": export_id,
                "request": request.to_dict(),
                "completed_files": sorted(completed),
                "current_file": rel,
                "source_offset": 0,
            },
        )
        write_status(
            root_path,
            progress=f"{len(completed)}/{total_specs}",
            active_operation="export",
            export_id=export_id,
            message=f"exporting {rel}",
        )
        if not src.exists():
            if spec.required:
                warnings.append(f"missing required log: {rel}")
            entries.append(
                ManifestFileEntry(
                    relative_path=rel,
                    kind=spec.kind,
                    size=0,
                    mtime=0.0,
                    sha256="",
                    line_count=0,
                    parser=spec.parser,
                    schema_version=spec.schema_version,
                    source_exists=False,
                    errors=["source missing"],
                )
            )
            completed.add(rel)
            continue
        try:
            exported = _export_one(src, dst, spec, filters, progress_path, request, export_id, completed)
            entries.append(exported)
            completed.add(rel)
            _write_progress(
                progress_path,
                {
                    "export_id": export_id,
                    "request": request.to_dict(),
                    "completed_files": sorted(completed),
                    "current_file": "",
                    "source_offset": 0,
                },
            )
        except Exception as exc:
            warnings.append(f"export failed for {rel}: {exc}")

    sqlite_entry = _export_sqlite_snapshot(root_path, files_dir, filters, warnings)
    if sqlite_entry is not None:
        entries.append(sqlite_entry)

    manifest = build_manifest(
        export_id=export_id,
        root=root_path,
        filters=filters,
        archive_format=archive_format,
        files=entries,
    )
    save_manifest(export_dir / "manifest.json", manifest)
    total_bytes = sum(entry.size for entry in entries)
    archive_paths: list[str] = []
    if archive_format:
        archive_result = archive_logs(export_dir, format=archive_format, verify=True)
        archive_paths = archive_result
    write_status(
        root_path,
        progress="completed",
        active_operation="",
        export_id=export_id,
        last_backup_time=datetime.now().isoformat(timespec="seconds"),
        archive_size=sum(Path(path).stat().st_size for path in archive_paths if Path(path).exists()),
        message="log export completed",
    )
    return ExportResult(
        export_id=export_id,
        export_dir=str(export_dir),
        manifest_path=str(export_dir / "manifest.json"),
        files_count=len([entry for entry in entries if entry.source_exists]),
        total_bytes=total_bytes,
        archive_paths=archive_paths,
        warnings=warnings,
    )


def discover_log_files(root: Path) -> list[LogFileSpec]:
    explicit = [
        LogFileSpec("workflow.log", "workflow", "log", required=True),
        LogFileSpec("iteration_log.csv", "simulate", "csv"),
        LogFileSpec("favorite_alphas.csv", "candidate", "csv"),
        LogFileSpec("local_alpha_library.csv", "candidate", "csv"),
        LogFileSpec("correlation_check.log", "metrics", "log"),
    ]
    directories = [
        ("logs", "workflow"),
        ("reward_shadow_logs", "reward"),
        ("migration_logs", "migration"),
        ("memory/evolution", "population"),
        ("memory/statistics", "metrics"),
        ("memory/failure_patterns", "failure"),
        ("memory/insights", "insight"),
    ]
    specs: dict[str, LogFileSpec] = {item.relative_path: item for item in explicit}
    for directory, kind in directories:
        base = root / directory
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            if path.name in {"log_manager_status.json"}:
                continue
            suffix = path.suffix.lower()
            if suffix not in {".log", ".json", ".jsonl", ".csv"}:
                continue
            rel = path.relative_to(root).as_posix()
            specs.setdefault(rel, LogFileSpec(rel, kind, _parser_for(path), _schema_for(rel)))
    return sorted(specs.values(), key=lambda item: item.relative_path)


def _export_sqlite_snapshot(
    root: Path,
    files_dir: Path,
    filters: dict[str, Any],
    warnings: list[str],
) -> ManifestFileEntry | None:
    db_path = root / "runtime" / "db" / "workflow.db"
    if not db_path.exists():
        return None
    rel = "runtime/db/workflow_snapshot.json"
    dst = files_dir / rel
    try:
        snapshot = export_memory_snapshot(db_path, alpha_id=str(filters.get("alpha_id") or ""))
        dst.parent.mkdir(parents=True, exist_ok=True)
        safe_atomic_write_json(dst, snapshot)
        sha, line_count = hash_and_count(dst)
        return ManifestFileEntry(
            relative_path=rel,
            kind="storage",
            size=dst.stat().st_size,
            mtime=db_path.stat().st_mtime,
            sha256=sha,
            line_count=line_count,
            parser="json",
            schema_version="sqlite_snapshot_v1",
            source_exists=True,
        )
    except Exception as exc:
        warnings.append(f"sqlite snapshot export failed: {exc}")
        return None


def _export_one(
    src: Path,
    dst: Path,
    spec: LogFileSpec,
    filters: dict[str, Any],
    progress_path: Path,
    request: ExportRequest,
    export_id: str,
    completed: set[str],
) -> ManifestFileEntry:
    if _has_filters(filters):
        if src.suffix.lower() in LINE_SUFFIXES:
            return _export_filtered_lines(src, dst, spec, filters, progress_path, request, export_id, completed)
        if src.suffix.lower() in JSON_SUFFIXES:
            return _export_filtered_json(src, dst, spec, filters)
    return _copy_full(src, dst, spec, progress_path, request, export_id, completed)


def _copy_full(
    src: Path,
    dst: Path,
    spec: LogFileSpec,
    progress_path: Path,
    request: ExportRequest,
    export_id: str,
    completed: set[str],
) -> ManifestFileEntry:
    dst.parent.mkdir(parents=True, exist_ok=True)
    partial = _partial_path(dst)
    offset = partial.stat().st_size if partial.exists() else 0
    mode = "ab" if offset else "wb"
    with src.open("rb") as in_fh, partial.open(mode) as out_fh:
        in_fh.seek(offset)
        while True:
            chunk = in_fh.read(4 * 1024 * 1024)
            if not chunk:
                break
            out_fh.write(chunk)
            offset += len(chunk)
            _write_progress(
                progress_path,
                {
                    "export_id": export_id,
                    "request": request.to_dict(),
                    "completed_files": sorted(completed),
                    "current_file": spec.relative_path,
                    "source_offset": offset,
                    "partial_path": str(partial),
                },
            )
    safe_replace(partial, dst)
    return _entry_from_exported(dst, src, spec)


def _export_filtered_lines(
    src: Path,
    dst: Path,
    spec: LogFileSpec,
    filters: dict[str, Any],
    progress_path: Path,
    request: ExportRequest,
    export_id: str,
    completed: set[str],
) -> ManifestFileEntry:
    dst.parent.mkdir(parents=True, exist_ok=True)
    partial = _partial_path(dst)
    source_offset = 0
    if partial.exists():
        try:
            state = _load_progress(progress_path)
            if state.get("current_file") == spec.relative_path:
                source_offset = int(state.get("source_offset") or 0)
        except Exception:
            source_offset = 0
    if src.suffix.lower() == ".csv":
        return _export_filtered_csv(src, dst, spec, filters, progress_path, request, export_id, completed)
    mode = "ab" if partial.exists() and source_offset else "wb"
    if mode == "wb":
        source_offset = 0
    with src.open("rb") as in_fh, partial.open(mode) as out_fh:
        in_fh.seek(source_offset)
        while True:
            raw = in_fh.readline()
            if not raw:
                break
            source_offset = in_fh.tell()
            text = raw.decode("utf-8-sig", errors="replace")
            if _matches_line(src, text, filters):
                out_fh.write(raw)
            _write_progress(
                progress_path,
                {
                    "export_id": export_id,
                    "request": request.to_dict(),
                    "completed_files": sorted(completed),
                    "current_file": spec.relative_path,
                    "source_offset": source_offset,
                    "partial_path": str(partial),
                },
            )
    safe_replace(partial, dst)
    entry = _entry_from_exported(dst, src, spec)
    if src.suffix.lower() == ".log":
        entry.filter_confidence = "low" if filters.get("alpha_id") or filters.get("worker_id") else "medium"
    if src.suffix.lower() == ".csv":
        entry.filter_confidence = "medium"
    return entry


def _export_filtered_csv(
    src: Path,
    dst: Path,
    spec: LogFileSpec,
    filters: dict[str, Any],
    progress_path: Path,
    request: ExportRequest,
    export_id: str,
    completed: set[str],
) -> ManifestFileEntry:
    dst.parent.mkdir(parents=True, exist_ok=True)
    partial = _partial_path(dst)
    with src.open("r", newline="", encoding="utf-8-sig", errors="replace") as in_fh:
        reader = csv.DictReader(in_fh)
        fieldnames = list(reader.fieldnames or [])
        with partial.open("w", newline="", encoding="utf-8") as out_fh:
            writer = csv.DictWriter(out_fh, fieldnames=fieldnames, extrasaction="ignore")
            if fieldnames:
                writer.writeheader()
            for index, row in enumerate(reader, start=2):
                payload = {str(key): value for key, value in row.items() if key is not None}
                payload["message"] = json.dumps(payload, ensure_ascii=False, default=str)
                if _matches_payload(payload, filters):
                    writer.writerow(payload)
                _write_progress(
                    progress_path,
                    {
                        "export_id": export_id,
                        "request": request.to_dict(),
                        "completed_files": sorted(completed),
                        "current_file": spec.relative_path,
                        "source_offset": 0,
                        "csv_line": index,
                        "partial_path": str(partial),
                    },
                )
    safe_replace(partial, dst)
    entry = _entry_from_exported(dst, src, spec)
    entry.filter_confidence = "medium"
    return entry


def _export_filtered_json(src: Path, dst: Path, spec: LogFileSpec, filters: dict[str, Any]) -> ManifestFileEntry:
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        payload = safe_json_read(src, None)
    except (OSError, json.JSONDecodeError):
        return _copy_full(src, dst, spec, dst.parent / PROGRESS_FILE, ExportRequest("", ""), "", set())
    if payload is None:
        return _copy_full(src, dst, spec, dst.parent / PROGRESS_FILE, ExportRequest("", ""), "", set())
    if isinstance(payload, list):
        payload = [item for item in payload if _matches_payload(item if isinstance(item, dict) else {}, filters)]
    elif isinstance(payload, dict) and not _snapshot_json(src):
        if not _matches_payload(payload, filters):
            payload = {}
    safe_atomic_write_json(dst, payload)
    return _entry_from_exported(dst, src, spec)


def _entry_from_exported(dst: Path, src: Path, spec: LogFileSpec) -> ManifestFileEntry:
    sha, line_count = hash_and_count(dst)
    stat = src.stat() if src.exists() else dst.stat()
    return ManifestFileEntry(
        relative_path=spec.relative_path,
        kind=spec.kind,
        size=dst.stat().st_size,
        mtime=stat.st_mtime,
        sha256=sha,
        line_count=line_count,
        parser=spec.parser,
        schema_version=spec.schema_version,
        source_exists=True,
    )


def _matches_line(path: Path, text: str, filters: dict[str, Any]) -> bool:
    payload: dict[str, Any] = {}
    suffix = path.suffix.lower()
    stripped = text.strip()
    if suffix == ".jsonl":
        try:
            loaded = json.loads(stripped)
            payload = loaded if isinstance(loaded, dict) else {}
        except json.JSONDecodeError:
            payload = {"message": text}
    elif suffix == ".log":
        parsed = parse_log_line(text)
        payload = {
            "timestamp": parsed.get("timestamp", ""),
            "message": parsed.get("message", text),
            "level": parsed.get("level", ""),
            "source": parsed.get("source", ""),
        }
    elif suffix == ".csv":
        try:
            row = next(csv.reader(io.StringIO(text)))
            payload = {"message": " ".join(row), "timestamp": row[0] if row else ""}
        except (csv.Error, StopIteration):
            payload = {"message": text}
    return _matches_payload(payload, filters, raw_text=text)


def _matches_payload(payload: dict[str, Any], filters: dict[str, Any], raw_text: str = "") -> bool:
    if not _has_filters(filters):
        return True
    haystack = raw_text or json.dumps(payload, ensure_ascii=False, default=str)
    for key in ["task_id", "alpha_id", "worker_id"]:
        needle = filters.get(key)
        if needle and str(needle) not in haystack and str(payload.get(key) or "") != str(needle):
            return False
    since = _parse_time(filters.get("since"))
    until = _parse_time(filters.get("until"))
    if since or until:
        timestamp = _payload_time(payload, haystack)
        if timestamp is None:
            return False
        if since and timestamp < since:
            return False
        if until and timestamp > until:
            return False
    return True


def _payload_time(payload: dict[str, Any], raw: str) -> datetime | None:
    for key in ["time", "timestamp", "created_at", "updated_at"]:
        value = payload.get(key)
        parsed = _parse_time(value)
        if parsed:
            return parsed
    for token in raw.replace(",", " ").split():
        parsed = _parse_time(token)
        if parsed:
            return parsed
    return None


def _parse_time(value: Any) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    text = text.replace("Z", "+00:00")
    for candidate in [text, text[:19]]:
        try:
            return datetime.fromisoformat(candidate)
        except ValueError:
            pass
    for fmt in ("%Y-%m-%d %H:%M:%S,%f", "%Y-%m-%d %H:%M:%S", "%Y%m%d_%H%M%S"):
        try:
            return datetime.strptime(text[:26], fmt)
        except ValueError:
            continue
    return None


def _time_text(value: str | datetime | None) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    return str(value) if value else None


def _has_filters(filters: dict[str, Any]) -> bool:
    return any(filters.get(key) for key in ["since", "until", "task_id", "alpha_id", "worker_id"])


def _parser_for(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".jsonl":
        return "reward" if "reward" in path.as_posix().lower() else "jsonl"
    if suffix == ".json":
        return "reward" if "reward" in path.as_posix().lower() else "json"
    if suffix == ".csv":
        return "csv"
    if suffix == ".log":
        return "log"
    return "raw"


def _schema_for(relative_path: str) -> str:
    path = relative_path.lower()
    if path.endswith("workflow_state.jsonl"):
        return "workflow_state_v1"
    if "reward_shadow" in path:
        return "reward_shadow_v1"
    if "migration" in path:
        return "migration_v1"
    if path.endswith("memory/insights/research_insights.json"):
        return "research_insight_v1"
    if path.endswith("memory/insights/insight_state.json"):
        return "insight_state_v1"
    if path.endswith(".csv"):
        return "csv_legacy"
    return "legacy"


def _snapshot_json(path: Path) -> bool:
    name = path.name.lower()
    return name in {"migration_state.json", "migration_metrics.json", "operator_statistics.json"}


def _partial_path(dst: Path) -> Path:
    return dst.with_name(f".{dst.name}.partial")


def _load_progress(path: Path) -> dict[str, Any]:
    payload = safe_json_read(path, {})
    return payload if isinstance(payload, dict) else {}


def _write_progress(path: Path, payload: dict[str, Any]) -> None:
    safe_atomic_write_json(path, payload)


def _existing_export_id(output_root: Path) -> str:
    if not output_root.exists():
        return ""
    candidates = sorted(
        [path for path in output_root.iterdir() if path.is_dir() and (path / PROGRESS_FILE).exists()],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        return ""
    progress = _load_progress(candidates[0] / PROGRESS_FILE)
    return str(progress.get("export_id") or candidates[0].name)
