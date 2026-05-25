from __future__ import annotations

import sqlite3
from types import SimpleNamespace

from wq_workflow.data.migrations import initialize_refactor_tables
from wq_workflow.observability.source_adapters import ExperimentMetricsAdapter, GovernanceMetricsAdapter, MLMetricsAdapter, OfflineMetricsAdapter, StrategyMetricsAdapter, SystemMetricsAdapter, WorkflowStatusAdapter


def _cfg(tmp_path):
    return SimpleNamespace(storage_db_path=str(tmp_path / "workflow.db"), observability_status_max_age_seconds=86400)


def test_observability_source_adapters_fail_open_and_collect(tmp_path):
    cfg = _cfg(tmp_path)
    conn = sqlite3.connect(cfg.storage_db_path)
    initialize_refactor_tables(conn)
    conn.execute("INSERT INTO strategy_budget_allocations (allocation_id, plan_id, strategy_id, suggested_ratio) VALUES ('a','p','s',0.5)")
    conn.commit(); conn.close()
    for cls in (WorkflowStatusAdapter, MLMetricsAdapter, GovernanceMetricsAdapter, ExperimentMetricsAdapter, OfflineMetricsAdapter, StrategyMetricsAdapter, SystemMetricsAdapter):
        result = cls(config=cfg, root=tmp_path).collect()
        assert "metrics" in result and "warnings" in result
    strategy = StrategyMetricsAdapter(config=cfg, root=tmp_path).collect()
    assert any(item["metric_name"] == "strategy.budget_allocation_count" and item["value"] == 1 for item in strategy["metrics"])
