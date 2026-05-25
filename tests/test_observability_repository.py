from __future__ import annotations

import sqlite3

from wq_workflow.observability.repository import ObservabilityRepository
from wq_workflow.observability.schema import ObservabilityMetric, ObservabilitySnapshot, ObservabilitySourceStatus, ObservabilitySummary


def test_observability_repository_crud(tmp_path):
    repo = ObservabilityRepository(conn=sqlite3.connect(tmp_path / "workflow.db"))
    assert repo.initialize()["ok"] is True
    metric = ObservabilityMetric(metric_id="m1", source="system", metric_name="system.status_file_count", value=1)
    assert repo.save_metric(metric) and repo.save_metric(metric)
    assert repo.list_metrics(source="system")[0].metric_id == "m1"
    status = ObservabilitySourceStatus(source="system", available=True, metric_count=1)
    assert repo.save_source_status(status)
    assert repo.list_source_statuses()[0].source == "system"
    snapshot = ObservabilitySnapshot(snapshot_id="s1", metrics=[metric], source_statuses=[status])
    summary = ObservabilitySummary(summary_id="sum1", total_metrics=1)
    assert repo.save_snapshot(snapshot) and repo.get_latest_snapshot().snapshot_id == "s1"
    assert repo.save_summary(summary) and repo.get_latest_summary().summary_id == "sum1"
