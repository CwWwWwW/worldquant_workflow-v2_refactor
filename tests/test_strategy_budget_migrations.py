from __future__ import annotations

import sqlite3

from wq_workflow.data.migrations import initialize_refactor_tables


def test_strategy_budget_migrations_repeatable_and_preserve_existing():
    conn = sqlite3.connect(":memory:")
    initialize_refactor_tables(conn)
    initialize_refactor_tables(conn)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"strategy_budget_rules", "strategy_budget_allocations", "strategy_budget_plans", "strategy_budget_reports"} <= tables
    assert {"strategy_portfolio_states", "strategy_scoreboards", "offline_replay_runs", "counterfactual_estimates"} <= tables
    indexes = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    assert "idx_strategy_budget_rules_type" in indexes
    assert "idx_strategy_budget_reports_generated_at" in indexes
