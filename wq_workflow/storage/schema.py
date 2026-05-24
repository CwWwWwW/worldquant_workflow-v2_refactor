from __future__ import annotations

import sqlite3


SCHEMA_VERSION = 2


DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS alpha_runs (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      alpha_id TEXT UNIQUE,
      expression TEXT,
      fitness REAL,
      sharpe REAL,
      turnover REAL,
      margin REAL,
      score REAL,
      result TEXT,
      created_at TEXT,
      raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS lineage (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      child_alpha TEXT,
      parent_alpha TEXT,
      mutation_type TEXT,
      operator_name TEXT,
      created_at TEXT,
      raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS operator_stats (
      operator_name TEXT PRIMARY KEY,
      success_count INTEGER DEFAULT 0,
      fail_count INTEGER DEFAULT 0,
      avg_reward REAL DEFAULT 0,
      last_used TEXT,
      raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS state_transitions (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      alpha_id TEXT,
      state_name TEXT,
      status TEXT,
      error TEXT,
      created_at TEXT,
      raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS evolution_memory (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      namespace TEXT DEFAULT 'legacy',
      memory_key TEXT,
      memory_value TEXT,
      score REAL,
      created_at TEXT,
      UNIQUE(namespace, memory_key)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS events (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      source_path TEXT,
      source TEXT,
      event_type TEXT,
      alpha_id TEXT,
      state TEXT,
      created_at TEXT,
      raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS candidate_pool (
      alpha_id TEXT PRIMARY KEY,
      expression TEXT,
      reward REAL,
      score REAL,
      passed INTEGER DEFAULT 0,
      created_at TEXT,
      updated_at TEXT,
      raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS failure_patterns (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      error_type TEXT,
      expression TEXT,
      root_cause TEXT,
      successful_fix TEXT,
      created_at TEXT,
      raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS storage_offsets (
      source_path TEXT PRIMARY KEY,
      size INTEGER,
      mtime REAL,
      line_no INTEGER DEFAULT 0,
      updated_at TEXT
    );
    """,
    "CREATE TABLE IF NOT EXISTS policy_memory (memory_key TEXT PRIMARY KEY, memory_value TEXT, score REAL, updated_at TEXT);",
    "CREATE TABLE IF NOT EXISTS reward_memory (memory_key TEXT PRIMARY KEY, memory_value TEXT, score REAL, updated_at TEXT);",
    "CREATE TABLE IF NOT EXISTS crossover_memory (memory_key TEXT PRIMARY KEY, memory_value TEXT, score REAL, updated_at TEXT);",
    "CREATE TABLE IF NOT EXISTS parent_selection_memory (memory_key TEXT PRIMARY KEY, memory_value TEXT, score REAL, updated_at TEXT);",
    "CREATE INDEX IF NOT EXISTS idx_alpha_id ON alpha_runs(alpha_id);",
    "CREATE INDEX IF NOT EXISTS idx_score ON alpha_runs(score);",
    "CREATE INDEX IF NOT EXISTS idx_created ON alpha_runs(created_at);",
    "CREATE INDEX IF NOT EXISTS idx_events_replay ON events(alpha_id, source, event_type, created_at);",
    "CREATE INDEX IF NOT EXISTS idx_events_source_created ON events(source_path, created_at);",
    "CREATE INDEX IF NOT EXISTS idx_lineage_child ON lineage(child_alpha);",
    "CREATE INDEX IF NOT EXISTS idx_state_created ON state_transitions(created_at);",
    """
    CREATE TABLE IF NOT EXISTS evolution_population (
      alpha_id TEXT PRIMARY KEY,
      expression TEXT NOT NULL,
      generation INTEGER DEFAULT 0,
      family TEXT DEFAULT 'unknown',
      reward REAL DEFAULT 0,
      survival_score REAL DEFAULT 0,
      long_term_value REAL DEFAULT 0,
      lineage_depth INTEGER DEFAULT 0,
      parent_ids TEXT,
      mutation_history TEXT,
      metrics TEXT,
      complexity TEXT,
      status TEXT DEFAULT 'active',
      birth_source TEXT DEFAULT 'unknown',
      created_at TEXT,
      updated_at TEXT,
      raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS evolution_generations (
      generation INTEGER PRIMARY KEY,
      population_size INTEGER DEFAULT 0,
      best_alpha_id TEXT,
      best_reward REAL DEFAULT 0,
      avg_reward REAL DEFAULT 0,
      avg_survival_score REAL DEFAULT 0,
      family_entropy REAL DEFAULT 0,
      diversity_score REAL DEFAULT 0,
      created_at TEXT,
      raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS evolution_policy_actions (
      action_type TEXT NOT NULL,
      action_name TEXT NOT NULL,
      context_key TEXT DEFAULT 'global',
      count INTEGER DEFAULT 0,
      reward_sum REAL DEFAULT 0,
      avg_reward REAL DEFAULT 0,
      success_count INTEGER DEFAULT 0,
      success_rate REAL DEFAULT 0,
      weight REAL DEFAULT 1.0,
      updated_at TEXT,
      raw_payload TEXT,
      PRIMARY KEY(action_type, action_name, context_key)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS evolution_decisions (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      generation INTEGER DEFAULT 0,
      alpha_id TEXT,
      candidate_alpha_id TEXT,
      decision_type TEXT,
      parent_a TEXT,
      parent_b TEXT,
      action_type TEXT,
      action_name TEXT,
      context_key TEXT,
      weights TEXT,
      selected_weight REAL DEFAULT 0,
      simulator_score REAL DEFAULT 0,
      skipped INTEGER DEFAULT 0,
      skipped_reason TEXT,
      reward REAL DEFAULT 0,
      reward_delta REAL DEFAULT 0,
      success INTEGER DEFAULT 0,
      created_at TEXT,
      raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS alpha_graph_edges (
      edge_type TEXT NOT NULL,
      src TEXT NOT NULL,
      dst TEXT NOT NULL,
      count INTEGER DEFAULT 0,
      reward_sum REAL DEFAULT 0,
      avg_reward REAL DEFAULT 0,
      success_count INTEGER DEFAULT 0,
      success_rate REAL DEFAULT 0,
      updated_at TEXT,
      raw_payload TEXT,
      PRIMARY KEY(edge_type, src, dst)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS lineage_values (
      alpha_id TEXT PRIMARY KEY,
      current_reward REAL DEFAULT 0,
      future_reward REAL DEFAULT 0,
      long_term_value REAL DEFAULT 0,
      descendant_count INTEGER DEFAULT 0,
      lookahead INTEGER DEFAULT 3,
      updated_at TEXT,
      raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS simulator_observations (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      alpha_id TEXT,
      expression TEXT,
      simulator_score REAL DEFAULT 0,
      flags TEXT,
      skipped INTEGER DEFAULT 0,
      skipped_reason TEXT,
      parent_reward REAL DEFAULT 0,
      created_at TEXT,
      raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS evolution_meta (
      meta_key TEXT PRIMARY KEY,
      meta_value TEXT,
      updated_at TEXT
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_evolution_population_score
    ON evolution_population(survival_score, long_term_value, reward);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_evolution_population_family
    ON evolution_population(family, status);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_evolution_decisions_action
    ON evolution_decisions(action_type, action_name, created_at);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_evolution_decisions_alpha
    ON evolution_decisions(alpha_id, candidate_alpha_id);
    """,
)


def initialize_schema(conn: sqlite3.Connection) -> None:
    conn.execute("BEGIN IMMEDIATE")
    try:
        for statement in DDL:
            conn.execute(statement)
        try:
            from wq_workflow.data.migrations import initialize_refactor_tables

            initialize_refactor_tables(conn)
        except Exception as exc:
            raise RuntimeError(f"refactor table initialization failed: {exc}") from exc
        conn.execute("PRAGMA user_version = %d" % SCHEMA_VERSION)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
