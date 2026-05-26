from __future__ import annotations

import sqlite3

from wq_workflow.data.migrations import initialize_refactor_tables


def test_explainability_migrations_repeatable_and_preserve_tables():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE legacy_full_import_completed(id TEXT)")
    initialize_refactor_tables(conn)
    initialize_refactor_tables(conn)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"observability_explanation_evidence", "observability_decision_traces", "observability_run_explanations", "observability_daily_reports", "observability_stage_reports"} <= tables
    assert {"observability_metrics", "observability_alert_events", "observability_health_reports", "strategy_budget_allocations"} <= tables
    indexes = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    assert "idx_observability_explanation_source" in indexes
    assert "idx_observability_daily_reports_date" in indexes
    assert "legacy_full_import_completed" in tables
