from __future__ import annotations

from wq_workflow.dashboard.status_aggregator import DashboardStatusAggregator
from wq_workflow.legacy_bridge.observer import LegacyIterationObserver


def test_dashboard_reads_legacy_bridge_first_and_readonly(tmp_path):
    observer = LegacyIterationObserver(root=tmp_path)
    observer.on_workflow_start()
    observer.on_template_selected(template_name="tpl", iteration=2)
    observer.on_reward_update(alpha_id="a", iteration=2, reward=0.6)
    before = (tmp_path / "runtime/status/runtime_state.json").read_text(encoding="utf-8")
    snapshot = DashboardStatusAggregator(root=tmp_path, include_db=False, include_logs=False).build_snapshot()
    after = (tmp_path / "runtime/status/runtime_state.json").read_text(encoding="utf-8")
    assert snapshot.runtime.current_state == "REWARD_UPDATE"
    assert snapshot.runtime.current_alpha_id == "a"
    assert snapshot.runtime.recent_events
    assert snapshot.runtime.legacy_evidence_summary
    assert before == after


def test_dashboard_missing_corrupt_runtime_not_fatal(tmp_path):
    path = tmp_path / "runtime/status/runtime_state.json"
    path.parent.mkdir(parents=True)
    path.write_text("{broken", encoding="utf-8")
    snapshot = DashboardStatusAggregator(root=tmp_path, include_db=False, include_logs=False).build_snapshot()
    assert snapshot.runtime.current_state in {"IDLE", "UNKNOWN"}
    assert snapshot.global_warnings
