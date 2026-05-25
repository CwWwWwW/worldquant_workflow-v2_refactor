from __future__ import annotations

import os
import time

from wq_workflow.observability.status_reader import StatusReader


def test_status_reader_safe_cases(tmp_path):
    reader = StatusReader()
    path = tmp_path / "status.json"
    path.write_text('{"value": 2}', encoding="utf-8")
    ok, payload, warnings = reader.read_status_if_exists(path)
    assert ok and payload["value"] == 2 and warnings == []
    assert reader.get_mtime_iso(path)
    assert reader.is_stale(path, 999999) is False
    missing_ok, _, missing_warnings = reader.read_status_if_exists(tmp_path / "missing.json")
    assert missing_ok is False and missing_warnings
    broken = tmp_path / "broken.json"
    broken.write_text('{bad', encoding="utf-8")
    before = broken.read_text(encoding="utf-8")
    ok, _, warnings = reader.read_status_if_exists(broken)
    assert ok is False and any("corrupt" in item for item in warnings)
    assert broken.read_text(encoding="utf-8") == before
    old = tmp_path / "old.json"
    old.write_text('{}', encoding="utf-8")
    os.utime(old, (time.time() - 10, time.time() - 10))
    assert reader.is_stale(old, 1) is True
