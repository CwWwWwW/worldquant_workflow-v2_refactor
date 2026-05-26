from __future__ import annotations

import json

from wq_workflow.dashboard.log_summarizer import LogSummarizer


def test_log_summarizer_extracts_states_alpha_errors_and_truncates(tmp_path):
    log = tmp_path / "state.jsonl"
    log.write_text(
        json.dumps({"time": "t1", "state": "WAIT_RESULT", "alpha_id": "a1"}) + "\n"
        + "2026-01-01 PARSE_RESULT alpha_id=a2 iteration=2\n"
        + "SC check alpha_id=a3\n"
        + "Traceback (most recent call last): " + "x" * 1000,
        encoding="utf-8",
    )
    summarizer = LogSummarizer()
    text = summarizer.read_tail(log, max_bytes=5_000)
    events = summarizer.extract_recent_events(text, limit=10)
    errors = summarizer.extract_error_summaries(text, limit=2)
    assert any(event["state"] == "WAIT_RESULT" for event in events)
    assert any(event["state"] == "PARSE_RESULT" for event in events)
    assert any(event["state"] == "PLATFORM_SC_CHECK" for event in events)
    assert any(event.get("alpha_id") == "a2" for event in events)
    assert errors and len(errors[-1]["message"]) < 350


def test_log_summarizer_missing_and_encoding_fail_open(tmp_path):
    summarizer = LogSummarizer()
    assert summarizer.read_tail(tmp_path / "missing.log") == ""
    bad = tmp_path / "bad.log"
    bad.write_bytes(b"\xff\xfeWAIT_RESULT")
    assert "WAIT_RESULT" in summarizer.read_tail(bad)
