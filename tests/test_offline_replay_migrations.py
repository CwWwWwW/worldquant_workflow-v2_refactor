import sqlite3

from wq_workflow.data.migrations import initialize_refactor_tables


def test_offline_replay_migration_tables_indexes_and_idempotency():
    conn = sqlite3.connect(":memory:")
    initialize_refactor_tables(conn)
    initialize_refactor_tables(conn)
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "offline_replay_runs" in tables
    assert "offline_replay_policy_decisions" in tables
    assert "offline_replay_policy_metrics" in tables
    assert "offline_replay_comparisons" in tables
    assert "decision_snapshots" in tables
    assert "experiment_records" in tables
    indexes = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    assert "idx_offline_replay_runs_status" in indexes
    assert "idx_offline_replay_policy_decisions_run_id" in indexes
    assert "idx_offline_replay_policy_metrics_run_id" in indexes
    assert "idx_offline_replay_comparisons_run_id" in indexes
