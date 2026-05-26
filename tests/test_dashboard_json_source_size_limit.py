from __future__ import annotations

import json
from pathlib import Path

from wq_workflow.dashboard.readonly_sources import DashboardReadonlySources


def test_small_json_source_reads_normally(tmp_path):
    path = tmp_path / "ok.json"
    path.write_text(json.dumps({"updated_at": "now", "value": 1}), encoding="utf-8")
    src = DashboardReadonlySources(root=tmp_path, max_json_bytes=1000)
    status, payload = src.read_json_source("ok", path)
    assert status.available is True
    assert payload["value"] == 1


def test_large_json_source_skips_without_reading_full_file(monkeypatch, tmp_path):
    path = tmp_path / "large.json"
    path.write_text('{"payload":"' + ("x" * 200) + '"}', encoding="utf-8")
    src = DashboardReadonlySources(root=tmp_path, max_json_bytes=10)

    def fail_read_text(self, *args, **kwargs):
        raise AssertionError("oversized JSON must not be read")

    monkeypatch.setattr(Path, "read_text", fail_read_text)
    status, payload = src.read_json_source("large_source", path)
    assert status.available is False
    assert payload == {}
    assert any(w.startswith("source_too_large:large_source:") for w in status.warnings)


def test_corrupt_json_source_warns_and_fails_open(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{bad", encoding="utf-8")
    src = DashboardReadonlySources(root=tmp_path, max_json_bytes=1000)
    status, payload = src.read_json_source("bad", path)
    assert status.available is False
    assert payload == {}
    assert any(w.startswith("read_failed:") for w in status.warnings)


def test_large_json_source_is_not_fatal(tmp_path):
    path = tmp_path / "large.json"
    path.write_text('{"payload":"' + ("x" * 200) + '"}', encoding="utf-8")
    src = DashboardReadonlySources(root=tmp_path, max_json_bytes=10)
    status, payload = src.read_json_source("large", path)
    assert status.available is False
    assert payload == {}
