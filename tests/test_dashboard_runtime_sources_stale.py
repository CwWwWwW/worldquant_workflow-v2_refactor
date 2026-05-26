from __future__ import annotations

import os
import time

from wq_workflow.dashboard.cli_formatter import CLIStatusFormatter
from wq_workflow.dashboard.readonly_sources import DashboardReadonlySources
from wq_workflow.dashboard.status_aggregator import DashboardStatusAggregator
from wq_workflow.legacy_bridge.evidence import LegacyLearningEvidenceBuilder, LegacyLearningEvidenceWriter
from wq_workflow.legacy_bridge.recent_events import RecentEventWriter
from wq_workflow.legacy_bridge.schema import RuntimeEvent


def _touch_old(path, seconds: int = 10) -> None:
    old = time.time() - seconds
    os.utime(path, (old, old))


def test_recent_events_stale_by_mtime(tmp_path):
    path = tmp_path / "runtime/status/recent_events.jsonl"
    writer = RecentEventWriter(path)
    assert writer.append_event(RuntimeEvent(event_type="WAIT_RESULT", message="fresh"))
    src = DashboardReadonlySources(root=tmp_path, stale_after_seconds=60)
    status, payload = src.read_recent_events_summary(limit=5)
    assert status.available is True
    assert status.stale is False
    assert payload["events"]

    _touch_old(path)
    src = DashboardReadonlySources(root=tmp_path, stale_after_seconds=1)
    status, _ = src.read_recent_events_summary(limit=5)
    assert status.available is True
    assert status.stale is True
    assert "stale_source:recent_events" in status.warnings


def test_legacy_learning_evidence_stale_by_mtime(tmp_path):
    path = tmp_path / "runtime/status/legacy_learning_evidence.jsonl"
    writer = LegacyLearningEvidenceWriter(path)
    assert writer.append_evidence(LegacyLearningEvidenceBuilder().from_backtest_result(alpha_id="a"))
    src = DashboardReadonlySources(root=tmp_path, stale_after_seconds=60)
    status, payload = src.read_legacy_evidence_summary(limit=5)
    assert status.available is True
    assert status.stale is False
    assert payload["by_type"]

    _touch_old(path)
    src = DashboardReadonlySources(root=tmp_path, stale_after_seconds=1)
    status, _ = src.read_legacy_evidence_summary(limit=5)
    assert status.available is True
    assert status.stale is True
    assert "stale_source:legacy_learning_evidence" in status.warnings


def test_missing_and_empty_runtime_sources(tmp_path):
    src = DashboardReadonlySources(root=tmp_path, stale_after_seconds=1)
    status, payload = src.read_recent_events_summary()
    assert status.available is False
    assert status.stale is False
    assert status.warnings == ["missing_source"]
    assert payload == {"events": []}

    empty = tmp_path / "runtime/status/legacy_learning_evidence.jsonl"
    empty.parent.mkdir(parents=True)
    empty.write_text("", encoding="utf-8")
    status, payload = src.read_legacy_evidence_summary()
    assert status.available is True
    assert status.stale is False
    assert status.summary["recent_count"] == 0
    assert payload == {"by_type": {}, "recent": []}


def test_dashboard_and_cli_include_stale_source_warning(tmp_path):
    path = tmp_path / "runtime/status/recent_events.jsonl"
    writer = RecentEventWriter(path)
    assert writer.append_event(RuntimeEvent(event_type="WAIT_RESULT", message="old"))
    _touch_old(path)

    sources = DashboardReadonlySources(root=tmp_path, status_files={}, stale_after_seconds=1)
    snapshot = DashboardStatusAggregator(root=tmp_path, include_db=False, include_logs=False, sources=sources).build_snapshot()
    assert "recent_events:stale_source:recent_events" in snapshot.global_warnings
    text = CLIStatusFormatter().format_snapshot(snapshot)
    assert "Warnings:" in text
    assert "stale_source:recent_events" in text
