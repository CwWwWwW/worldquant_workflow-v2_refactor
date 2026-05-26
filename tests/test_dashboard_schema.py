from __future__ import annotations

import json

from wq_workflow.dashboard.dashboard_schema import (
    DashboardMLStatus,
    DashboardObservabilityStatus,
    DashboardRuntimeStatus,
    DashboardSnapshot,
    DashboardSourceStatus,
    DashboardStrategyStatus,
)


def test_dashboard_schema_to_dict_json_safe():
    snapshot = DashboardSnapshot(
        generated_at="now",
        runtime=DashboardRuntimeStatus(generated_at="now", current_state="WAIT_RESULT", recent_events=[{"x": float("nan")}]),
        ml=DashboardMLStatus(model_enabled=True, ml_parameters={"nan": float("nan")}),
        strategy=DashboardStrategyStatus(champion="legacy"),
        observability=DashboardObservabilityStatus(metrics_available=True, key_findings=["ok"]),
        sources=[DashboardSourceStatus(source="s", available=True, summary={"v": float("inf")})],
    )
    data = snapshot.to_dict()
    assert data["runtime"]["current_state"] == "WAIT_RESULT"
    assert data["ml"]["ml_parameters"]["nan"] is None
    assert data["sources"][0]["summary"]["v"] is None
    json.dumps(data)


def test_dashboard_schema_defaults_do_not_fail():
    assert DashboardRuntimeStatus().to_dict()["current_state"] is None
    assert DashboardMLStatus().to_dict()["model_count"] is None
    assert DashboardStrategyStatus().to_dict()["budget_allocations"] == []
    assert DashboardObservabilityStatus().to_dict()["alert_count"] == 0
