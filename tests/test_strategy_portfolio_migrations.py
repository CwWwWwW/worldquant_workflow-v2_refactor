import sqlite3

from wq_workflow.data.migrations import initialize_refactor_tables


def test_strategy_portfolio_migrations_repeatable(tmp_path):
    conn = sqlite3.connect(tmp_path / "workflow.db")
    initialize_refactor_tables(conn)
    initialize_refactor_tables(conn)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"strategy_portfolio_states", "strategy_portfolio_transitions", "strategy_portfolios", "strategy_portfolio_reports"} <= tables
    assert {"strategy_scoreboards", "offline_replay_runs", "counterfactual_estimates"} <= tables
    indexes = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    assert "idx_strategy_portfolio_states_state" in indexes
    assert "idx_strategy_portfolio_reports_generated_at" in indexes
    conn.close()
