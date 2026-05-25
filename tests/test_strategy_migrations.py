import sqlite3

from wq_workflow.data.migrations import initialize_refactor_tables


def test_strategy_migrations_tables_indexes_repeatable(tmp_path):
    conn = sqlite3.connect(tmp_path / "workflow.db")
    initialize_refactor_tables(conn)
    initialize_refactor_tables(conn)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"strategy_profiles", "strategy_evidence", "strategy_signals", "strategy_scores", "strategy_scoreboards"} <= tables
    assert {"decision_snapshots", "offline_replay_runs", "counterfactual_estimates", "strategy_registry"} <= tables
    indexes = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    assert "idx_strategy_profiles_type" in indexes
    assert "idx_strategy_scoreboards_generated_at" in indexes
    conn.close()
