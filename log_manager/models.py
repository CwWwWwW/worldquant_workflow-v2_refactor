from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class LogFileSpec:
    relative_path: str
    kind: str
    parser: str
    schema_version: str = "legacy"
    required: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ExportRequest:
    root: str
    output_dir: str
    since: str | None = None
    until: str | None = None
    task_id: str | None = None
    alpha_id: str | None = None
    worker_id: str | None = None
    archive_format: str = "zip"
    resume: bool = True

    def filters(self) -> dict[str, str | None]:
        return {
            "since": self.since,
            "until": self.until,
            "task_id": self.task_id,
            "alpha_id": self.alpha_id,
            "worker_id": self.worker_id,
        }

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ImportRequest:
    source: str
    target_root: str
    mode: str = "offline"
    resume: bool = True
    conflict_policy: str = "keep_existing"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ManifestFileEntry:
    relative_path: str
    kind: str
    size: int
    mtime: float
    sha256: str
    line_count: int
    parser: str
    schema_version: str
    exported_from_offset: int = 0
    source_exists: bool = True
    filter_confidence: str = "high"
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ManifestFileEntry":
        return cls(
            relative_path=str(payload.get("relative_path") or ""),
            kind=str(payload.get("kind") or "unknown"),
            size=int(payload.get("size") or 0),
            mtime=float(payload.get("mtime") or 0.0),
            sha256=str(payload.get("sha256") or ""),
            line_count=int(payload.get("line_count") or 0),
            parser=str(payload.get("parser") or "raw"),
            schema_version=str(payload.get("schema_version") or "legacy"),
            exported_from_offset=int(payload.get("exported_from_offset") or 0),
            source_exists=bool(payload.get("source_exists", True)),
            filter_confidence=str(payload.get("filter_confidence") or "high"),
            errors=list(payload.get("errors") or []),
        )


@dataclass(slots=True)
class ArchiveEntry:
    path: str
    size: int
    sha256: str
    index: int = 1
    total_parts: int = 1
    format: str = "zip"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ExportResult:
    export_id: str
    export_dir: str
    manifest_path: str
    files_count: int
    total_bytes: int
    archive_paths: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ImportResult:
    mode: str
    target_dir: str
    imported_files: list[str] = field(default_factory=list)
    skipped_files: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class FileIntegrityReport:
    relative_path: str
    status: str
    size: int = 0
    sha256: str = ""
    line_count: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class IntegrityReport:
    status: str
    checked_at: str
    files: list[FileIntegrityReport] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "checked_at": self.checked_at,
            "files": [item.to_dict() for item in self.files],
            "errors": self.errors,
            "warnings": self.warnings,
            "summary": self.summary,
        }


@dataclass(slots=True)
class ReplayEvent:
    timestamp: str
    source: str
    event_type: str
    alpha_id: str
    state: str
    payload: dict[str, Any]
    original_path: str
    line_no: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class LogManagerStatus:
    progress: str = "idle"
    archive_size: int = 0
    integrity_status: str = "unknown"
    last_backup_time: str = ""
    active_operation: str = ""
    export_id: str = ""
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "LogManagerStatus":
        if not isinstance(payload, dict):
            return cls()
        return cls(
            progress=str(payload.get("progress") or "idle"),
            archive_size=int(payload.get("archive_size") or 0),
            integrity_status=str(payload.get("integrity_status") or "unknown"),
            last_backup_time=str(payload.get("last_backup_time") or ""),
            active_operation=str(payload.get("active_operation") or ""),
            export_id=str(payload.get("export_id") or ""),
            message=str(payload.get("message") or ""),
        )
