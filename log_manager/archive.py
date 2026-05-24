from __future__ import annotations

import tarfile
import zipfile
from pathlib import Path

from .manifest import load_manifest, save_manifest, sha256_file, write_status
from .models import ArchiveEntry
from utils.safe_json import safe_replace


def archive_logs(
    export_dir: str | Path,
    format: str = "zip",
    volume_size_mb: int = 1024,
    verify: bool = True,
) -> list[str]:
    export_path = Path(export_dir).resolve()
    if format not in {"zip", "tar.gz", ""}:
        raise ValueError("format must be 'zip' or 'tar.gz'")
    if not format:
        return []
    archive_path = export_path.with_suffix(".zip" if format == "zip" else ".tar.gz")
    tmp_archive = archive_path.with_name(f".{archive_path.name}.tmp")
    if tmp_archive.exists():
        tmp_archive.unlink()
    if format == "zip":
        _write_zip(export_path, tmp_archive)
    else:
        _write_tar_gz(export_path, tmp_archive)
    safe_replace(tmp_archive, archive_path)
    paths = _split_archive(archive_path, volume_size_mb, format)
    entries: list[ArchiveEntry] = []
    total = len(paths)
    for index, path_text in enumerate(paths, start=1):
        path = Path(path_text)
        entries.append(
            ArchiveEntry(
                path=path.name,
                size=path.stat().st_size,
                sha256=sha256_file(path),
                index=index,
                total_parts=total,
                format=format,
            )
        )
    manifest_path = export_path / "manifest.json"
    if manifest_path.exists():
        manifest = load_manifest(manifest_path)
        manifest["archive_entries"] = [entry.to_dict() for entry in entries]
        save_manifest(manifest_path, manifest)
    if verify:
        for path_text, entry in zip(paths, entries):
            if sha256_file(Path(path_text)) != entry.sha256:
                raise IOError(f"archive verification failed: {path_text}")
    root = _root_from_manifest(export_path)
    if root:
        write_status(
            root,
            archive_size=sum(entry.size for entry in entries),
            active_operation="archive",
            message=f"archived {export_path.name}",
        )
    return paths


def _write_zip(export_path: Path, archive_path: Path) -> None:
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
        for path in sorted(export_path.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(export_path.parent).as_posix())


def _write_tar_gz(export_path: Path, archive_path: Path) -> None:
    with tarfile.open(archive_path, "w:gz") as tf:
        tf.add(export_path, arcname=export_path.name, recursive=True)


def _split_archive(archive_path: Path, volume_size_mb: int, format: str) -> list[str]:
    volume_size = max(1, int(volume_size_mb)) * 1024 * 1024
    size = archive_path.stat().st_size
    if size <= volume_size:
        return [str(archive_path)]
    paths: list[str] = []
    index = 1
    with archive_path.open("rb") as src:
        while True:
            chunk = src.read(volume_size)
            if not chunk:
                break
            part = archive_path.with_name(f"{archive_path.name}.part{index:03d}")
            with part.open("wb") as dst:
                dst.write(chunk)
            paths.append(str(part))
            index += 1
    archive_path.unlink()
    return paths


def _root_from_manifest(export_path: Path) -> Path | None:
    try:
        manifest = load_manifest(export_path / "manifest.json")
        root = manifest.get("filters", {}).get("root") or manifest.get("root")
        if root:
            return Path(root)
    except Exception:
        return None
    return None
