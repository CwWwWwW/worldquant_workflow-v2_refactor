from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from wq_workflow.time_utils import utc_now, utc_now_iso


def test_utc_now_helper_is_timezone_aware_utc_iso():
    now = utc_now()
    assert now.tzinfo is UTC

    value = utc_now_iso(timespec="seconds")
    parsed = datetime.fromisoformat(value)
    assert parsed.tzinfo is not None
    assert parsed.utcoffset().total_seconds() == 0


def test_no_deprecated_utc_now_call_in_source():
    root = Path(__file__).resolve().parents[1]
    skipped = {
        ".git",
        ".pytest_cache",
        "__pycache__",
        "logs",
        "ui_logs",
        "migration_logs",
        "runtime",
        "build",
        "dist",
        "release",
    }
    needle = "datetime." + "utcnow"
    offenders: list[str] = []

    for path in root.rglob("*.py"):
        if any(part in skipped for part in path.parts):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if needle in text:
            offenders.append(str(path.relative_to(root)))

    assert offenders == []
