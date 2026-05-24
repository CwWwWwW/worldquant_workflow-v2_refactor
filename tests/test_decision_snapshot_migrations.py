import sqlite3

from wq_workflow.data.migrations import initialize_refactor_tables


def test_decision_snapshot_tables_indexes_idempotent_and_legacy_safe(tmp_path):
    conn = sqlite3.connect(tmp_path / "workflow.db")
    conn.execute("CREATE TABLE IF NOT EXISTS evolution_meta (key TEXT PRIMARY KEY, value TEXT)")
    conn.execute("INSERT OR REPLACE INTO evolution_meta VALUES ('legacy_full_import_completed', '1')")
    initialize_refactor_tables(conn)
    initialize_refactor_tables(conn)
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"decision_snapshots", "decision_outcomes", "decision_snapshot_summaries", "experiment_records"}.issubset(tables)
    indexes = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    assert "idx_decision_snapshots_alpha_id" in indexes
    assert "idx_decision_snapshot_summaries_type" in indexes
    row = conn.execute("SELECT value FROM evolution_meta WHERE key='legacy_full_import_completed'").fetchone()
    assert row[0] == "1"
