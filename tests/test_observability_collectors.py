from __future__ import annotations

from wq_workflow.observability.collectors import BaseMetricsCollector


class GoodAdapter:
    def collect(self):
        return {"source": "system", "available": True, "metrics": [{"metric_name": "system.status_file_count", "value": 1}], "warnings": []}


class BadAdapter:
    def collect(self):
        raise RuntimeError("boom")


def test_collector_generates_metric_and_failure_is_source_warning():
    metrics, status = BaseMetricsCollector(adapter=GoodAdapter()).collect()
    assert metrics and metrics[0].source == "system" and metrics[0].timestamp
    assert status.available is True and status.metric_count == 1
    metrics, status = BaseMetricsCollector(adapter=BadAdapter()).collect()
    assert metrics == [] and status.available is False and status.warnings
