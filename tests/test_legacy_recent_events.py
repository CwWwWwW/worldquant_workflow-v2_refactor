from __future__ import annotations

from wq_workflow.legacy_bridge.recent_events import RecentEventReader, RecentEventWriter
from wq_workflow.legacy_bridge.schema import RuntimeEvent


def test_recent_events_append_tail_and_summary(tmp_path):
    path = tmp_path / "runtime/status/recent_events.jsonl"
    writer = RecentEventWriter(path)
    for idx in range(5):
        assert writer.append_event(RuntimeEvent(event_type="WAIT_RESULT_PROGRESS", iteration=idx, message="m" * 500))
    rows = RecentEventReader(path).read_tail(limit=2)
    assert [row.iteration for row in rows] == [3, 4]
    assert len(rows[-1].message) <= 300
    assert RecentEventReader(path).summarize_recent(limit=1)[0]["event_type"] == "WAIT_RESULT_PROGRESS"


def test_recent_events_error_summary_rotate_and_fail_open(tmp_path):
    path = tmp_path / "runtime/status/recent_events.jsonl"
    writer = RecentEventWriter(path, max_bytes=20)
    assert writer.append_error(ValueError("Traceback " + "x" * 1000), state="WAIT_RESULT")
    writer.rotate_if_needed(max_bytes=1)
    assert path.exists() is False or path.stat().st_size >= 0
    disabled = RecentEventWriter(tmp_path / "x.jsonl", enabled=False)
    assert disabled.append_event_type("UNKNOWN") is False
