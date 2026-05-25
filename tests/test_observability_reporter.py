from __future__ import annotations

import json

from wq_workflow.observability.reporter import ObservabilityReporter
from wq_workflow.observability.schema import ObservabilityMetric, ObservabilitySnapshot, ObservabilitySourceStatus, ObservabilitySummary


def test_observability_reporter_writes_and_backs_up_corrupt(tmp_path):
    status_path = tmp_path / "runtime" / "status" / "observability_metrics.json"
    reporter = ObservabilityReporter(status_path, root=tmp_path)
    metric = ObservabilityMetric(metric_id="m", source="system", metric_name="system.status_file_count", value=1)
    status = ObservabilitySourceStatus(source="system", available=True, metric_count=1)
    snapshot = ObservabilitySnapshot(snapshot_id="s", metrics=[metric], source_statuses=[status])
    summary = ObservabilitySummary(summary_id="sum", total_metrics=1, available_sources=1)
    assert reporter.update(snapshot, summary)["ok"] is True
    payload = json.loads(status_path.read_text(encoding="utf-8"))
    assert {"summary", "sources", "metrics", "warnings"} <= set(payload)
    status_path.write_text("{bad", encoding="utf-8")
    assert reporter.update(snapshot, summary)["ok"] is True
    assert list(status_path.parent.glob("observability_metrics.json.broken.*.bak"))
