import sqlite3
from wq_workflow.data.migrations import initialize_refactor_tables


def test_counterfactual_migration_tables_indexes_repeatable():
    conn=sqlite3.connect(':memory:')
    initialize_refactor_tables(conn); initialize_refactor_tables(conn)
    tables={r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for name in {'counterfactual_requests','counterfactual_evidence','counterfactual_estimates','counterfactual_summaries','decision_snapshots','offline_replay_runs'}:
        assert name in tables
    indexes={r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    assert 'idx_counterfactual_estimates_verdict' in indexes
    conn.execute("CREATE TABLE IF NOT EXISTS evolution_meta (key TEXT PRIMARY KEY, value TEXT)")
    conn.execute("INSERT OR REPLACE INTO evolution_meta VALUES ('legacy_full_import_completed','1')")
    initialize_refactor_tables(conn)
    assert conn.execute("SELECT value FROM evolution_meta WHERE key='legacy_full_import_completed'").fetchone()[0]=='1'
