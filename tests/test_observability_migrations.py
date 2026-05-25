from __future__ import annotations

import sqlite3

from wq_workflow.data.migrations import initialize_refactor_tables


def test_observability_migrations_repeatable_and_preserve_existing():
    conn = sqlite3.connect(":memory:")
    initialize_refactor_tables(conn)
    initialize_refactor_tables(conn)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"observability_metrics", "observability_source_status", "observability_snapshots", "observability_summaries"} <= tables
    assert {"strategy_budget_allocations", "offline_replay_runs", "counterfactual_estimates", "decision_snapshots"} <= tables
    indexes = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    assert "idx_observability_metrics_source" in indexes
    assert "idx_observability_summaries_generated_at" in indexes
