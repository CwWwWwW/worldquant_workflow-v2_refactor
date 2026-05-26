from __future__ import annotations

from types import SimpleNamespace

from wq_workflow.legacy_bridge.observer import LegacyIterationObserver
from wq_workflow.observability.source_adapters import WorkflowStatusAdapter


def test_observability_adapter_reads_legacy_state_summary(tmp_path):
    observer = LegacyIterationObserver(root=tmp_path)
    observer.on_workflow_start()
    observer.on_reward_update(alpha_id="a", iteration=3, reward=0.4)
    config = SimpleNamespace(
        storage_db_path="runtime/db/workflow.db",
        legacy_runtime_state_path="runtime/status/runtime_state.json",
        legacy_recent_events_path="runtime/status/recent_events.jsonl",
        observability_status_max_age_seconds=86400,
    )
    result = WorkflowStatusAdapter(config=config, root=tmp_path).collect()
    names = {metric["metric_name"]: metric["value"] for metric in result["metrics"]}
    assert names["workflow.runtime_state_available"] is True
    assert names["workflow.latest_iteration"] == 3
    assert names["workflow.recent_event_count"] >= 1
    assert result["raw_payload"]["runtime_state"]["current_alpha_id"] == "a"


def test_observability_missing_runtime_not_fatal(tmp_path):
    result = WorkflowStatusAdapter(config=SimpleNamespace(storage_db_path="runtime/db/workflow.db"), root=tmp_path).collect()
    assert result["available"] is False
    assert result["warnings"]
