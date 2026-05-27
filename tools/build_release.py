from __future__ import annotations

import fnmatch
import subprocess
import zipfile
from pathlib import Path

PROJECT_NAME = "worldquant_workflow-v2_refactor"

INCLUDE_DIRS = {
    "wq_workflow",
    "tools",
    "tests",
    "ui",
    "memory",
    "log_manager",
    "utils",
    "docs",
}

INCLUDE_FILES = {
    "README.md",
    "LICENSE",
    "NOTICE",
    "DISCLAIMER.md",
    "SECURITY.md",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "requirements.txt",
    "pytest.ini",
    "config.example.json",
    "run_workflow.bat",
    "worldquant_auto_workflow.py",
}

EXCLUDE_DIRS = {
    ".git",
    ".github",
    "runtime",
    "logs",
    "ui_logs",
    "migration_logs",
    "screenshots",
    "failure_artifacts",
    "artifacts",
    "iterations",
    "favorites",
    "exports",
    "reports",
    "returns",
    "reward_shadow_logs",
    "dist",
    "build",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".venv",
    "venv",
    "env",
    "browser_state",
    "cookies",
    "credentials",
    "secrets",
    "playwright-report",
    "test-results",
    ".tmp_pytest",
}

EXCLUDE_NAMES = {
    "config.json",
    ".env",
    "storage_state.json",
    "cookies.json",
    ".coverage",
}

EXCLUDE_SUFFIXES = {
    ".db",
    ".sqlite",
    ".sqlite3",
    ".db-wal",
    ".db-shm",
    ".log",
    ".pyc",
    ".pyo",
    ".tmp",
    ".bak",
    ".old",
    ".zip",
    ".7z",
}

EXCLUDE_PATTERNS = {
    ".env.*",
    "*.secret",
    "*.secrets",
    "*.local.json",
    "*.disabled.json",
}


def _run_git(root: Path, args: list[str]) -> str | None:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except Exception:
        return None
    return completed.stdout.strip()


def get_version(root: Path) -> str:
    tag = _run_git(root, ["describe", "--tags", "--exact-match"])
    return tag if tag else "dev"


def is_excluded(path: Path) -> bool:
    parts = path.parts
    if any(part in EXCLUDE_DIRS for part in parts[:-1]):
        return True
    name = path.name
    if name in EXCLUDE_NAMES:
        return True
    lower_name = name.lower()
    if any(lower_name.endswith(suffix) for suffix in EXCLUDE_SUFFIXES):
        return True
    rel = path.as_posix()
    return any(fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(rel, pattern) for pattern in EXCLUDE_PATTERNS)


def is_included(path: Path) -> bool:
    if path.as_posix() in INCLUDE_FILES:
        return True
    return bool(path.parts) and path.parts[0] in INCLUDE_DIRS


def git_files(root: Path) -> list[Path] | None:
    output = _run_git(root, ["ls-files", "--cached", "--others", "--exclude-standard"])
    if output is None:
        return None
    return [Path(line) for line in output.splitlines() if line.strip()]


def filesystem_files(root: Path) -> list[Path]:
    paths: list[Path] = []
    for base in sorted(INCLUDE_DIRS):
        directory = root / base
        if directory.exists():
            paths.extend(path.relative_to(root) for path in directory.rglob("*") if path.is_file())
    for filename in sorted(INCLUDE_FILES):
        path = root / filename
        if path.is_file():
            paths.append(path.relative_to(root))
    return sorted(set(paths))


def collect_files(root: Path) -> tuple[list[Path], int]:
    candidates = git_files(root)
    if candidates is None:
        candidates = filesystem_files(root)

    included: list[Path] = []
    excluded_count = 0
    for rel in sorted(set(candidates), key=lambda p: p.as_posix()):
        if is_excluded(rel):
            excluded_count += 1
            continue
        if not is_included(rel):
            excluded_count += 1
            continue
        if (root / rel).is_file():
            included.append(rel)
        else:
            excluded_count += 1
    return included, excluded_count


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    version = get_version(root)
    dist_dir = root / "dist"
    dist_dir.mkdir(exist_ok=True)
    zip_path = dist_dir / f"{PROJECT_NAME}-{version}.zip"

    files, excluded_count = collect_files(root)
    if not files:
        print("ERROR: no files selected for release archive")
        return 2

    archive_root = f"{PROJECT_NAME}-{version}"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for rel in files:
            source = root / rel
            arcname = Path(archive_root) / rel
            zf.write(source, arcname.as_posix())

    print(f"Release zip: {zip_path}")
    print(f"Included files: {len(files)}")
    print(f"Excluded files: {excluded_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
