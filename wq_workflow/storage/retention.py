from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class RetentionResult:
    deleted: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def prune_artifacts(
    root: str | Path,
    *,
    retention_days: int = 14,
    keep_failure_artifacts: int = 200,
    keep_trace_artifacts: int = 100,
    keep_iteration_screenshots: int = 500,
) -> RetentionResult:
    root = Path(root)
    result = RetentionResult()
    cutoff = time.time() - max(1, int(retention_days)) * 24 * 3600
    specs = [
        (root / "logs" / "failures", "*.png", keep_failure_artifacts),
        (root / "logs" / "failures", "*.html", keep_failure_artifacts),
        (root / "logs" / "traces", "*.zip", keep_trace_artifacts),
        (root / "iterations", "*.png", keep_iteration_screenshots),
    ]
    for directory, pattern, keep in specs:
        _prune_directory(directory, pattern, cutoff=cutoff, keep=keep, result=result)
    return result


def _prune_directory(directory: Path, pattern: str, *, cutoff: float, keep: int, result: RetentionResult) -> None:
    try:
        files = [path for path in directory.glob(pattern) if path.is_file()]
    except OSError as exc:
        result.errors.append(f"{directory}:{exc}")
        return
    files.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    keep_set = set(files[: max(0, int(keep))])
    for path in files:
        try:
            if path in keep_set and path.stat().st_mtime >= cutoff:
                continue
            path.unlink()
            result.deleted.append(str(path))
        except OSError as exc:
            result.errors.append(f"{path}:{exc}")
