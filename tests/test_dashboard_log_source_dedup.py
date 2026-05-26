from __future__ import annotations

from wq_workflow.dashboard.readonly_sources import DashboardReadonlySources


def test_same_resolved_log_path_read_once(monkeypatch, tmp_path):
    log = tmp_path / "workflow.log"
    log.write_text("2026-01-01T00:00:00 INFO WAIT_RESULT alpha_id=a1\n", encoding="utf-8")
    src = DashboardReadonlySources(root=tmp_path, log_paths=[log, tmp_path / "." / "workflow.log"])
    assert len(src.log_paths) == 1

    calls = []
    original = src.log_summarizer.read_tail

    def wrapped(path, *args, **kwargs):
        calls.append(path)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(src.log_summarizer, "read_tail", wrapped)
    status, summary = src.read_log_summary(limit=5)
    assert status.available is True
    assert len(calls) == 1
    assert len(summary["events"]) == 1


def test_duplicate_log_events_are_summarized_once(tmp_path):
    line = "2026-01-01T00:00:00 ERROR WAIT_RESULT alpha_id=a1 duplicated\n"
    log1 = tmp_path / "workflow.log"
    log2 = tmp_path / "logs" / "workflow.log"
    log2.parent.mkdir()
    log1.write_text(line, encoding="utf-8")
    log2.write_text(line, encoding="utf-8")
    src = DashboardReadonlySources(root=tmp_path, log_paths=[log1, log2])
    status, summary = src.read_log_summary(limit=10)
    assert status.available is True
    assert len(summary["events"]) == 1


def test_different_log_events_are_retained(tmp_path):
    log1 = tmp_path / "workflow.log"
    log2 = tmp_path / "logs" / "workflow.log"
    log2.parent.mkdir()
    log1.write_text("2026-01-01T00:00:00 INFO WAIT_RESULT alpha_id=a1 one\n", encoding="utf-8")
    log2.write_text("2026-01-01T00:00:01 INFO PARSE_RESULT alpha_id=a2 two\n", encoding="utf-8")
    src = DashboardReadonlySources(root=tmp_path, log_paths=[log1, log2])
    _, summary = src.read_log_summary(limit=10)
    assert len(summary["events"]) == 2


def test_missing_logs_are_fail_open(tmp_path):
    src = DashboardReadonlySources(root=tmp_path, log_paths=[tmp_path / "missing.log"])
    status, summary = src.read_log_summary(limit=10)
    assert status.available is False
    assert summary == {"events": [], "errors": []}


def test_log_summary_uses_tail_reader(monkeypatch, tmp_path):
    log = tmp_path / "workflow.log"
    log.write_text("x" * 300_000 + "\nWAIT_RESULT alpha_id=a1\n", encoding="utf-8")
    src = DashboardReadonlySources(root=tmp_path, log_paths=[log])
    seen = {}
    original = src.log_summarizer.read_tail

    def wrapped(path, *, max_bytes=200_000):
        seen["max_bytes"] = max_bytes
        return original(path, max_bytes=max_bytes)

    monkeypatch.setattr(src.log_summarizer, "read_tail", wrapped)
    status, summary = src.read_log_summary()
    assert status.available is True
    assert seen["max_bytes"] == 200_000
    assert summary["events"]
