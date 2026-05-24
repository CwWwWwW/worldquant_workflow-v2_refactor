import sqlite3

from wq_workflow.data.migrations import initialize_refactor_tables
from wq_workflow.storage.schema import initialize_schema


KEY_TABLES = {
    "ml_model_registry",
    "ml_prediction_audit",
    "ml_training_samples",
    "decision_snapshots",
    "sc_training_samples",
    "parent_selection_samples",
    "policy_training_samples",
    "simulator_training_samples",
    "strategy_registry",
    "strategy_performance",
    "drift_events",
    "insight_usage",
    "insight_effect_samples",
}


def _columns(conn, table):
    return [(row[1], row[2]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]


def test_storage_schema_and_migrations_create_same_refactor_tables(tmp_path):
    storage_conn = sqlite3.connect(tmp_path / "storage.db")
    migration_conn = sqlite3.connect(tmp_path / "migration.db")
    initialize_schema(storage_conn)
    initialize_refactor_tables(migration_conn)

    for table in KEY_TABLES:
        assert _columns(storage_conn, table) == _columns(migration_conn, table)

    initialize_schema(storage_conn)
    initialize_refactor_tables(migration_conn)
    storage_conn.close()
    migration_conn.close()


def test_schema_initialization_preserves_legacy_tables_and_meta(tmp_path):
    conn = sqlite3.connect(tmp_path / "workflow.db")
    conn.execute("CREATE TABLE legacy_table (id TEXT PRIMARY KEY)")
    conn.execute("INSERT INTO legacy_table VALUES ('keep')")
    conn.commit()
    initialize_schema(conn)
    conn.execute(
        "INSERT OR REPLACE INTO evolution_meta (meta_key, meta_value, updated_at) VALUES (?, ?, ?)",
        ("legacy_full_import_completed", "true", "old"),
    )
    conn.commit()

    initialize_schema(conn)
    assert conn.execute("SELECT id FROM legacy_table").fetchone()[0] == "keep"
    assert conn.execute("SELECT meta_value FROM evolution_meta WHERE meta_key='legacy_full_import_completed'").fetchone()[0] == "true"
    conn.close()
