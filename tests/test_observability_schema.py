from __future__ import annotations

import json

from wq_workflow.observability.schema import ObservabilityMetric, ObservabilitySnapshot, ObservabilitySourceStatus, ObservabilitySummary


def test_observability_schema_roundtrip_json_safe():
    metric = ObservabilityMetric(metric_id="m1", source="strategy_budget", metric_name="strategy.budget_allocation_count", metric_type="gauge", value=3, unit="count")
    assert ObservabilityMetric.from_dict(metric.to_dict()).to_dict()["value"] == 3
    status = ObservabilitySourceStatus(source="strategy_budget", available=True, table_names=["strategy_budget_allocations"], warnings=[])
    assert ObservabilitySourceStatus.from_dict(status.to_dict()).available is True
    snapshot = ObservabilitySnapshot(snapshot_id="s1", metrics=[metric], source_statuses=[status], summary={"x": 1})
    assert ObservabilitySnapshot.from_dict(snapshot.to_dict()).metrics[0].metric_name
    summary = ObservabilitySummary(summary_id="sum1", total_metrics=1, available_sources=1)
    data = summary.to_dict()
    assert data["generated_at"].endswith("+00:00")
    json.dumps({"metric": metric.to_dict(), "summary": data})
