from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .repository import AlphaRepository, EventRepository, LineageRepository, OffsetRepository, source_path_for
from .schema import initialize_schema
from .sqlite_store import connect_db
from .write_queue import _write_snapshot


@dataclass(slots=True)
class MigrationResult:
    imported_events: int = 0
    imported_json_snapshots: int = 0
    imported_lineage_rows: int = 0
    skipped_bad_lines: int = 0
    skipped_existing_lines: int = 0
    files: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def migrate_root(root: str | Path, db_path: str | Path | None = None) -> MigrationResult:
    from ..paths import WORKFLOW_DB_FILE

    root = Path(root).resolve()
    db = Path(db_path or (root / "runtime" / "db" / "workflow.db") or WORKFLOW_DB_FILE)
    conn = connect_db(db)
    try:
        initialize_schema(conn)
        result = MigrationResult()
        for path in _jsonl_files(root):
            _migrate_jsonl_file(conn, root, path, result)
        for path in _json_files(root):
            _migrate_json_file(conn, root, path, result)
        return result
    finally:
        conn.close()


def migrate_alpha_jsonl(path: str | Path, db_path: str | Path, *, root: str | Path | None = None) -> MigrationResult:
    path = Path(path)
    root_path = Path(root or path.parent).resolve()
    conn = connect_db(db_path)
    try:
        initialize_schema(conn)
        result = MigrationResult()
        _migrate_jsonl_file(conn, root_path, path, result)
        return result
    finally:
        conn.close()


def _jsonl_files(root: Path) -> list[Path]:
    bases = [root / "logs", root / "reward_shadow_logs", root / "migration_logs"]
    result: list[Path] = []
    for base in bases:
        if base.exists():
            result.extend(path for path in base.rglob("*.jsonl") if path.is_file())
    return sorted(result)


def _json_files(root: Path) -> list[Path]:
    bases = [root / "memory" / "evolution", root / "memory" / "statistics", root / "memory" / "failure_patterns"]
    result: list[Path] = []
    for base in bases:
        if base.exists():
            result.extend(path for path in base.rglob("*.json") if path.is_file())
    return sorted(result)


def _migrate_jsonl_file(conn, root: Path, path: Path, result: MigrationResult) -> None:
    rel = source_path_for(path, root=root)
    offsets = OffsetRepository(conn)
    stat = path.stat()
    previous = offsets.get_offset(rel)
    start_line = 0
    if previous and int(previous.get("size") or 0) <= stat.st_size:
        start_line = int(previous.get("line_no") or 0)
    event_rows: list[tuple[str, dict[str, Any]]] = []
    alpha_rows: list[dict[str, Any]] = []
    last_line = 0
    try:
        with path.open("r", encoding="utf-8-sig", errors="replace") as fh:
            for line_no, line in enumerate(fh, start=1):
                last_line = line_no
                if line_no <= start_line:
                    result.skipped_existing_lines += 1
                    continue
                try:
                    loaded = json.loads(line)
                except json.JSONDecodeError:
                    result.skipped_bad_lines += 1
                    continue
                if not isinstance(loaded, dict):
                    result.skipped_bad_lines += 1
                    continue
                event_rows.append((path, loaded))
                if _looks_like_alpha(loaded):
                    alpha_rows.append(loaded)
        conn.execute("BEGIN IMMEDIATE")
        try:
            EventRepository(conn, root=root).batch_insert_events(event_rows)
            AlphaRepository(conn).batch_insert(alpha_rows)
            offsets.set_offset(rel, size=stat.st_size, mtime=stat.st_mtime, line_no=last_line)
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        result.imported_events += len(event_rows)
        if event_rows:
            result.files.append(rel)
    except Exception as exc:
        result.errors.append(f"{rel}:{exc}")


def _migrate_json_file(conn, root: Path, path: Path, result: MigrationResult) -> None:
    rel = source_path_for(path, root=root)
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig", errors="replace"))
    except Exception as exc:
        result.errors.append(f"{rel}:{exc}")
        return
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            _write_snapshot(conn, path, payload)
            if path.name.lower() == "alpha_lineage.json" and isinstance(payload, list):
                repo = LineageRepository(conn)
                for row in payload:
                    if isinstance(row, dict):
                        repo.add_lineage(payload=row)
                        result.imported_lineage_rows += 1
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        result.imported_json_snapshots += 1
        result.files.append(rel)
    except Exception as exc:
        result.errors.append(f"{rel}:{exc}")


def _looks_like_alpha(payload: dict[str, Any]) -> bool:
    return bool(
        payload.get("alpha_id")
        and (
            payload.get("expression")
            or payload.get("code")
            or payload.get("expression_after")
            or isinstance(payload.get("metrics"), dict)
        )
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import legacy WorldQuant JSON/JSONL memory into SQLite.")
    parser.add_argument("--root", default=".", help="Workflow project root.")
    parser.add_argument("--db", default="", help="SQLite database path. Defaults to runtime/db/workflow.db under root.")
    args = parser.parse_args(argv)
    result = migrate_root(args.root, args.db or None)
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 1 if result.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
