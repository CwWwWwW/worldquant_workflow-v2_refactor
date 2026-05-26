from __future__ import annotations

from wq_workflow.legacy_bridge.observer import LegacyIterationObserver
from wq_workflow.legacy_bridge.recent_events import RecentEventReader
from wq_workflow.legacy_bridge.runtime_state import RuntimeStateReader


def test_observer_hooks_write_state_events_evidence_fail_open(tmp_path):
    observer = LegacyIterationObserver(root=tmp_path)
    assert observer.on_workflow_start() is None
    observer.on_template_selected(template_name="tpl", template_family="fam", iteration=1)
    observer.on_wait_result_progress(alpha_id="a", iteration=1, platform_progress=0.5)
    observer.on_parse_result_done(alpha_id="a", iteration=1, parse_status="done", metrics={"sharpe": 1.1})
    observer.on_sc_check_done(alpha_id="a", iteration=1, platform_sc={"status": "complete", "abs_max": 0.2})
    observer.on_reward_update(alpha_id="a", iteration=1, reward=0.8)
    observer.on_recoverable_error(message="Traceback " + "x" * 1000)
    observer.on_fatal_error(message="fatal")
    ok, snapshot, _ = RuntimeStateReader(tmp_path / "runtime/status/runtime_state.json").read_snapshot()
    assert ok and snapshot and snapshot.current_state == "ERROR_FATAL"
    events = RecentEventReader(tmp_path / "runtime/status/recent_events.jsonl").read_tail(20)
    assert any(event.event_type == "REWARD_UPDATE" for event in events)
    assert observer.get_status()["enabled"] is True


def test_observer_write_exception_fail_open(tmp_path, monkeypatch):
    observer = LegacyIterationObserver(root=tmp_path)
    monkeypatch.setattr(observer.state_writer, "write_fail_open", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    assert observer.on_workflow_start() is None
    assert "last_error" in observer.get_status()
