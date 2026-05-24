from __future__ import annotations

import csv
import json
import shutil
import tarfile
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from .manifest import hash_and_count, load_manifest, manifest_entries, save_manifest, sha256_file, write_status
from .models import FileIntegrityReport, IntegrityReport
from .parsers.jsonl_parser import iter_jsonl
from .parsers.reward_parser import iter_reward_entries


def verify_integrity(
    path_or_archive: str | Path,
    report_path: str | Path | None = None,
) -> IntegrityReport:
    source = Path(path_or_archive).resolve()
    temp_dir: Path | None = None
    errors: list[str] = []
    warnings: list[str] = []
    try:
        try:
            export_dir = _resolve_export_dir(source)
            if export_dir is None:
                temp_dir = Path(tempfile.mkdtemp(prefix="log_manager_verify_"))
                export_dir = _extract_archive(source, temp_dir)
            manifest_path = export_dir / "manifest.json"
            if not manifest_path.exists():
                raise FileNotFoundError(f"manifest not found: {manifest_path}")
            manifest = load_manifest(manifest_path)
            if manifest.get("schema_version") != "log_manager_manifest_v1":
                warnings.append(f"manifest schema warning: {manifest.get('schema_version')}")
            reports: list[FileIntegrityReport] = []
            for entry in manifest_entries(manifest):
                reports.append(_verify_file(export_dir, entry.to_dict()))
            archive_warnings = _verify_archives(source, export_dir, manifest)
            warnings.extend(archive_warnings)
            file_errors = [error for report in reports for error in report.errors]
            status = "ok" if not errors and not file_errors else "failed"
            report = IntegrityReport(
                status=status,
                checked_at=datetime.now().isoformat(timespec="seconds"),
                files=reports,
                errors=errors + file_errors,
                warnings=warnings + [warning for report in reports for warning in report.warnings],
                summary={
                    "files_checked": len(reports),
                    "files_ok": sum(1 for item in reports if item.status == "ok"),
                    "files_failed": sum(1 for item in reports if item.status != "ok"),
                },
            )
            output = Path(report_path) if report_path else export_dir / "integrity_report.json"
            save_manifest(output, report.to_dict())
            root = _manifest_root(manifest)
            if root:
                write_status(root, integrity_status=status, active_operation="", message="integrity verification completed")
            return report
        except Exception as exc:
            report = IntegrityReport(
                status="failed",
                checked_at=datetime.now().isoformat(timespec="seconds"),
                errors=[f"integrity verification failed: {exc}"],
                summary={"files_checked": 0, "files_ok": 0, "files_failed": 0},
            )
            output = Path(report_path) if report_path else _default_report_path(source)
            save_manifest(output, report.to_dict())
            return report
    finally:
        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)


def _verify_file(export_dir: Path, entry: dict[str, Any]) -> FileIntegrityReport:
    relative = str(entry.get("relative_path") or "")
    path = export_dir / "files" / relative
    errors: list[str] = []
    warnings: list[str] = []
    if not entry.get("source_exists", True):
        return FileIntegrityReport(relative, "missing_source", errors=list(entry.get("errors") or []))
    if not path.exists():
        return FileIntegrityReport(relative, "failed", errors=["missing exported file"])
    sha, line_count = hash_and_count(path)
    size = path.stat().st_size
    if size != int(entry.get("size") or 0):
        errors.append(f"size mismatch: expected {entry.get('size')} got {size}")
    if sha != str(entry.get("sha256") or ""):
        errors.append("sha256 mismatch")
    parser = str(entry.get("parser") or "")
    if parser in {"jsonl", "reward"} or path.suffix.lower() == ".jsonl":
        for line_no, _raw, _payload, error in iter_jsonl(path):
            if error:
                errors.append(f"jsonl line {line_no}: {error}")
    if parser == "csv" or path.suffix.lower() == ".csv":
        warnings.extend(_check_csv(path))
    if parser == "reward" or "reward" in relative.lower():
        for line_no, _payload, reward_errors in iter_reward_entries(path):
            for error in reward_errors:
                errors.append(f"reward line {line_no}: {error}")
    status = "ok" if not errors else "failed"
    return FileIntegrityReport(relative, status, size=size, sha256=sha, line_count=line_count, errors=errors, warnings=warnings)


def _check_csv(path: Path) -> list[str]:
    warnings: list[str] = []
    try:
        with path.open("r", newline="", encoding="utf-8-sig", errors="replace") as fh:
            reader = csv.DictReader(fh)
            if not reader.fieldnames:
                warnings.append("missing csv header")
                return warnings
            expected = len(reader.fieldnames)
            for line_no, row in enumerate(reader, start=2):
                if row is None:
                    warnings.append(f"empty csv row {line_no}")
                    continue
                if None in row:
                    warnings.append(f"broken csv row {line_no}: extra columns")
                if len(row) < expected:
                    warnings.append(f"broken csv row {line_no}: missing columns")
    except csv.Error as exc:
        warnings.append(f"csv error: {exc}")
    except OSError as exc:
        warnings.append(f"csv read failed: {exc}")
    return warnings


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
    return _resolve_export_dir(temp_dir) or temp_dir


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


def _verify_archives(source: Path, export_dir: Path, manifest: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    archive_entries = manifest.get("archive_entries") or []
    if not archive_entries:
        return warnings
    base = source.parent if source.is_file() else export_dir.parent
    for entry in archive_entries:
        if not isinstance(entry, dict):
            continue
        path = base / str(entry.get("path") or "")
        if not path.exists():
            warnings.append(f"archive part missing: {path.name}")
            continue
        expected = str(entry.get("sha256") or "")
        if expected and sha256_file(path) != expected:
            warnings.append(f"archive part sha256 mismatch: {path.name}")
    return warnings


def _manifest_root(manifest: dict[str, Any]) -> Path | None:
    root = manifest.get("root")
    if root:
        return Path(str(root))
    return None


def _default_report_path(source: Path) -> Path:
    if source.is_dir():
        return source / "integrity_report.json"
    return source.with_name("integrity_report.json")


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
