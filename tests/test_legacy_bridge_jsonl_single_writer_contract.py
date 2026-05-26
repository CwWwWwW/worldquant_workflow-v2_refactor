from __future__ import annotations

import json
from pathlib import Path

from wq_workflow.legacy_bridge import utils
from wq_workflow.legacy_bridge.recent_events import RecentEventReader


def test_append_jsonl_direct_writes_record_and_optional_fsync(monkeypatch, tmp_path):
    path = tmp_path / "runtime/status/recent_events.jsonl"
    fsync_calls: list[int] = []
    monkeypatch.setattr(utils.os, "fsync", lambda fileno: fsync_calls.append(fileno))
    assert utils.append_jsonl_direct(path, {"event_type": "WAIT_RESULT"}, fsync=True)
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert rows == [{"event_type": "WAIT_RESULT"}]
    assert fsync_calls


def test_rotate_failure_is_fail_open(monkeypatch, tmp_path):
    path = tmp_path / "runtime/status/recent_events.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text("x" * 20, encoding="utf-8")
    monkeypatch.setattr(utils.shutil, "move", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("locked")))
    assert utils.append_jsonl_direct(path, {"event_type": "PARSE_RESULT"}, max_bytes=1)
    assert "PARSE_RESULT" in path.read_text(encoding="utf-8")


def test_jsonl_reader_skips_bad_and_partial_lines_once(tmp_path):
    path = tmp_path / "runtime/status/recent_events.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps({"event_type": "WAIT_RESULT"}) + "\n"
        "{bad json\n"
        '{"event_type": "PARSE_RESULT"',
        encoding="utf-8",
    )
    reader = RecentEventReader(path)
    rows = reader.read_raw_tail(limit=10)
    assert [row["event_type"] for row in rows] == ["WAIT_RESULT"]
    assert reader.warnings == ["bad_jsonl_line_skipped"]


def test_readme_documents_single_writer_contract():
    bridge = Path("wq_workflow/legacy_bridge/README.md").read_text(encoding="utf-8")
    root = Path("README.md").read_text(encoding="utf-8")
    combined = bridge + "\n" + root
    assert "one main-process writer" in combined or "single main-process writer" in combined
    assert "different `runtime/status` directory" in combined
    assert "Dashboard, CLI, observability" in combined


def test_dashboard_and_observability_do_not_append_bridge_jsonl():
    for folder in (Path("wq_workflow/dashboard"), Path("wq_workflow/observability")):
        for path in folder.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            assert "append_jsonl_direct" not in text
            assert "RecentEventWriter" not in text
            assert "LegacyLearningEvidenceWriter" not in text
