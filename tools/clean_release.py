from __future__ import annotations

import argparse
import shutil
from pathlib import Path


SKIP_DIR_NAMES = {".git", ".venv", "venv"}

REMOVE_DIR_NAMES = {
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}

REMOVE_TOP_LEVEL_DIRS = {
    "logs",
    "ui_logs",
    "migration_logs",
}

REMOVE_RUNTIME_CHILDREN = {
    "db",
    "models",
    "status",
    "audit",
    "tmp",
    "cache",
    "screenshots",
    "failures",
    "logs",
}

REMOVE_FILE_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".tmp",
    ".bak",
    ".old",
}

REMOVE_FILE_NAMES = {
    ".coverage",
}

KEEP_DIRS = (
    "runtime",
    "runtime/db",
    "runtime/logs",
    "logs",
)


def _is_skipped(path: Path, root: Path) -> bool:
    try:
        rel_parts = path.resolve().relative_to(root).parts
    except ValueError:
        rel_parts = path.parts
    return any(part in SKIP_DIR_NAMES for part in rel_parts)


def collect_targets(root: Path) -> list[Path]:
    root = root.resolve()
    targets: list[Path] = []

    for path in root.rglob("*"):
        if _is_skipped(path, root):
            continue

        if path.is_dir() and path.name in REMOVE_DIR_NAMES:
            targets.append(path)
            continue

        if path.is_file() and path.name in REMOVE_FILE_NAMES:
            targets.append(path)
            continue

        if path.is_file() and path.suffix in REMOVE_FILE_SUFFIXES:
            targets.append(path)
            continue

    for name in REMOVE_TOP_LEVEL_DIRS:
        path = root / name
        if path.exists():
            targets.append(path)

    runtime = root / "runtime"
    if runtime.exists():
        for child in REMOVE_RUNTIME_CHILDREN:
            path = runtime / child
            if path.exists():
                targets.append(path)

    return sorted(set(targets), key=lambda p: len(p.parts), reverse=True)


def remove_target(path: Path) -> tuple[bool, str]:
    try:
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()
        return True, ""
    except Exception as exc:
        return False, str(exc)


def ensure_keep_dirs(root: Path) -> None:
    for rel in KEEP_DIRS:
        path = root / rel
        path.mkdir(parents=True, exist_ok=True)
        gitkeep = path / ".gitkeep"
        if not gitkeep.exists():
            gitkeep.write_text("", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Clean cache/runtime artifacts before packaging a release.")
    parser.add_argument("--root", default=".", help="project root to clean")
    parser.add_argument("--apply", action="store_true", help="actually delete files; default is dry-run")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    if not root.exists() or not root.is_dir():
        print(f"ERROR project root does not exist or is not a directory: {root}")
        return 2

    targets = collect_targets(root)

    print(f"Project root: {root}")
    print(f"Targets: {len(targets)}")

    for target in targets:
        print(f"{'DELETE' if args.apply else 'DRY-RUN'} {target}")

    if not args.apply:
        print("Dry-run only. Use --apply to delete.")
        return 0

    failed = 0
    for target in targets:
        ok, err = remove_target(target)
        if not ok:
            failed += 1
            print(f"WARNING failed to remove {target}: {err}")

    ensure_keep_dirs(root)
    print(f"Clean completed, failed={failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
