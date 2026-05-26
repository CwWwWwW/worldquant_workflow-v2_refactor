from __future__ import annotations

import json
import os
import time

from wq_workflow.dashboard.status_aggregator import DashboardStatusAggregator


def test_dashboard_observability_sources_available_and_stale(tmp_path):
    status = tmp_path / "runtime" / "status"
    status.mkdir(parents=True)
    for name, payload in {
        "observability_metrics.json": {"updated_at": "now"},
        "observability_alerts.json": {"alert_count": 1, "warning_count": 1},
        "health_diagnosis.json": {"overall_status": "ok"},
        "run_explain_report.json": {"key_findings": ["finding"]},
        "daily_observability_report.json": {"recommended_human_checks": ["check"]},
        "stage7_summary_report.json": {"stage_name": "phase7"},
    }.items():
        path = status / name
        path.write_text(json.dumps(payload), encoding="utf-8")
    old_path = status / "observability_metrics.json"
    old = time.time() - 10
    os.utime(old_path, (old, old))
    snapshot = DashboardStatusAggregator(root=tmp_path, stale_after_seconds=1, include_db=False, include_logs=False).build_snapshot()
    assert snapshot.observability.metrics_available is True
    assert snapshot.observability.alert_count == 1
    assert snapshot.observability.explainability_available is True
    assert any(source.source == "observability_metrics" and source.stale for source in snapshot.sources)
