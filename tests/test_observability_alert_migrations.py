from __future__ import annotations

import sqlite3

from wq_workflow.data.migrations import initialize_refactor_tables


def test_observability_alert_migrations_repeatable():
    conn = sqlite3.connect(":memory:")
    initialize_refactor_tables(conn)
    initialize_refactor_tables(conn)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"observability_drift_rules", "observability_drift_signals", "observability_alert_rules", "observability_alert_events", "observability_health_diagnoses", "observability_health_reports"} <= tables
    assert {"observability_metrics", "strategy_budget_allocations"} <= tables
    indexes = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    assert "idx_observability_drift_rules_metric" in indexes
    assert "idx_observability_health_reports_generated_at" in indexes
