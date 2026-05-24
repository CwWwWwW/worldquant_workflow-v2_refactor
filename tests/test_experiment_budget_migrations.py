from __future__ import annotations

import sqlite3

from wq_workflow.data.migrations import initialize_refactor_tables


def test_budget_migrations_tables_indexes_and_legacy_meta(tmp_path):
    conn = sqlite3.connect(tmp_path / "workflow.db")
    conn.execute("CREATE TABLE IF NOT EXISTS evolution_meta (key TEXT PRIMARY KEY, value TEXT, updated_at TEXT)")
    conn.execute("INSERT OR REPLACE INTO evolution_meta(key, value) VALUES (?, ?)", ("legacy_full_import_completed", "true"))
    initialize_refactor_tables(conn)
    initialize_refactor_tables(conn)
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"experiment_budget_plans", "experiment_budget_allocations", "experiment_budget_snapshots"} <= tables
    assert {"experiment_plans", "experiment_assignments", "experiment_results", "experiment_summaries"} <= tables
    indexes = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    assert "idx_experiment_budget_plans_experiment_id" in indexes
    assert "idx_experiment_budget_allocations_plan_id" in indexes
    assert "idx_experiment_budget_snapshots_experiment_id" in indexes
    assert conn.execute("SELECT value FROM evolution_meta WHERE key=?", ("legacy_full_import_completed",)).fetchone()[0] == "true"
