from __future__ import annotations

from wq_workflow.legacy_bridge.evidence import LegacyLearningEvidenceBuilder, LegacyLearningEvidenceReader, LegacyLearningEvidenceWriter
from wq_workflow.legacy_bridge.recent_events import RecentEventReader, RecentEventWriter
from wq_workflow.legacy_bridge.schema import RuntimeEvent


def test_jsonl_append_bad_line_skip_redact_and_truncate(tmp_path):
    events = tmp_path / "runtime/status/recent_events.jsonl"
    writer = RecentEventWriter(events)
    assert writer.append_event(RuntimeEvent(event_type="WAIT_RESULT", message="x" * 1000, raw_payload={"api_key": "secret", "html": "h" * 1000}))
    with events.open("a", encoding="utf-8") as fh:
        fh.write("{bad json\n")
    assert writer.append_event(RuntimeEvent(event_type="PARSE_RESULT", message="ok"))

    reader = RecentEventReader(events)
    rows = reader.read_tail(limit=10)
    assert [row.event_type for row in rows] == ["WAIT_RESULT", "PARSE_RESULT"]
    assert reader.warnings == ["bad_jsonl_line_skipped"]
    assert len(rows[0].message) <= 300
    assert rows[0].raw_payload["api_key"] == "[REDACTED]"


def test_learning_evidence_bad_line_and_append_failure_fail_open(tmp_path):
    path = tmp_path / "runtime/status/legacy_learning_evidence.jsonl"
    writer = LegacyLearningEvidenceWriter(path)
    assert writer.append_evidence(LegacyLearningEvidenceBuilder().from_backtest_result(alpha_id="a", raw_payload={"token": "secret", "prompt": "p" * 1000}))
    path.write_text(path.read_text(encoding="utf-8") + "not-json\n", encoding="utf-8")

    reader = LegacyLearningEvidenceReader(path)
    rows = reader.read_tail(limit=10)
    assert len(rows) == 1
    assert reader.warnings == ["bad_jsonl_line_skipped"]
    assert rows[0].raw_payload["token"] == "[REDACTED]"

    parent_file = tmp_path / "not_a_dir"
    parent_file.write_text("x", encoding="utf-8")
    assert LegacyLearningEvidenceWriter(parent_file / "x.jsonl").append_evidence(rows[0]) is False
