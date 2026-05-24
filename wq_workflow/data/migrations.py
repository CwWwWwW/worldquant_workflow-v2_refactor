from __future__ import annotations

import sqlite3


REFRACTOR_TABLE_DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS ml_model_registry (
        model_id TEXT PRIMARY KEY,
        task_name TEXT,
        model_version TEXT,
        model_path TEXT,
        feature_schema_json TEXT,
        train_sample_count INTEGER,
        validation_metric_json TEXT,
        is_active INTEGER DEFAULT 0,
        created_at TEXT,
        raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS ml_prediction_audit (
        prediction_id TEXT PRIMARY KEY,
        task_name TEXT,
        alpha_id TEXT,
        model_version TEXT,
        features_json TEXT,
        prediction_json TEXT,
        confidence REAL,
        final_decision TEXT,
        final_source TEXT,
        created_at TEXT,
        raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS ml_training_samples (
        sample_id TEXT PRIMARY KEY,
        task_name TEXT,
        alpha_id TEXT,
        features_json TEXT,
        label_json TEXT,
        context_json TEXT,
        raw_payload TEXT,
        created_at TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS ml_model_events (
        event_id TEXT PRIMARY KEY,
        task_name TEXT,
        model_version TEXT,
        event_type TEXT,
        severity TEXT,
        message TEXT,
        action_taken TEXT,
        raw_payload TEXT,
        created_at TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS ml_online_evaluation (
        eval_id TEXT PRIMARY KEY,
        task_name TEXT,
        model_version TEXT,
        window_start TEXT,
        window_end TEXT,
        sample_count INTEGER,
        prediction_count INTEGER,
        success_count INTEGER,
        failure_count INTEGER,
        mae REAL,
        rmse REAL,
        precision_score REAL,
        recall_score REAL,
        hit_rate REAL,
        avg_reward_delta REAL,
        avg_sc_error REAL,
        drift_score REAL,
        degradation_score REAL,
        recommended_action TEXT,
        raw_payload TEXT,
        created_at TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS decision_snapshots (
        decision_id TEXT PRIMARY KEY,
        decision_type TEXT,
        alpha_id TEXT,
        context_json TEXT,
        available_actions_json TEXT,
        chosen_action_json TEXT,
        action_scores_json TEXT,
        selection_reason TEXT,
        legacy_score REAL,
        model_score REAL,
        propensity REAL,
        model_version TEXT,
        created_at TEXT,
        raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS decision_outcomes (
        outcome_id TEXT PRIMARY KEY,
        decision_id TEXT,
        decision_type TEXT,
        alpha_id TEXT,
        reward REAL,
        reward_delta REAL,
        success INTEGER,
        failure_type TEXT,
        platform_sc_abs_max REAL,
        metrics_json TEXT,
        created_at TEXT,
        raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS sc_training_samples (
        sample_id TEXT PRIMARY KEY,
        alpha_id TEXT,
        expression TEXT,
        platform_sc_abs_max REAL,
        platform_sc_status TEXT,
        features_json TEXT,
        label_json TEXT,
        context_json TEXT,
        raw_payload TEXT,
        created_at TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS parent_selection_samples (
        sample_id TEXT PRIMARY KEY,
        parent_alpha_id TEXT,
        child_alpha_id TEXT,
        parent_features_json TEXT,
        child_metrics_json TEXT,
        child_reward REAL,
        reward_delta REAL,
        child_success INTEGER,
        child_platform_sc_abs_max REAL,
        mutation_type TEXT,
        created_at TEXT,
        raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS policy_training_samples (
        sample_id TEXT PRIMARY KEY,
        decision_id TEXT,
        alpha_id TEXT,
        context_json TEXT,
        available_actions_json TEXT,
        chosen_action_json TEXT,
        reward_delta REAL,
        success INTEGER,
        failure_type TEXT,
        platform_sc_abs_max REAL,
        created_at TEXT,
        raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS simulator_training_samples (
        sample_id TEXT PRIMARY KEY,
        alpha_id TEXT,
        features_json TEXT,
        prediction_json TEXT,
        backtest_success INTEGER,
        quality_passed INTEGER,
        reward REAL,
        fitness REAL,
        sharpe REAL,
        turnover REAL,
        failure_type TEXT,
        created_at TEXT,
        raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS experiment_records (
        experiment_id TEXT PRIMARY KEY,
        experiment_type TEXT,
        base_alpha_id TEXT,
        controlled_variable TEXT,
        hypothesis TEXT,
        status TEXT,
        created_at TEXT,
        raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS insight_usage (
        usage_id TEXT PRIMARY KEY,
        insight_id TEXT,
        alpha_id TEXT,
        prompt_context_json TEXT,
        created_at TEXT,
        raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS insight_effect_samples (
        effect_id TEXT PRIMARY KEY,
        insight_id TEXT,
        alpha_id TEXT,
        reward REAL,
        fitness REAL,
        sharpe REAL,
        turnover REAL,
        platform_sc_abs_max REAL,
        created_at TEXT,
        raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS drift_events (
        event_id TEXT PRIMARY KEY,
        drift_type TEXT,
        severity TEXT,
        metric_name TEXT,
        event_json TEXT,
        created_at TEXT,
        raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS strategy_registry (
        strategy_id TEXT PRIMARY KEY,
        strategy_type TEXT,
        role TEXT,
        task_name TEXT,
        model_version TEXT,
        status TEXT,
        created_at TEXT,
        updated_at TEXT,
        raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS strategy_performance (
        record_id TEXT PRIMARY KEY,
        strategy_id TEXT,
        window_name TEXT,
        sample_count INTEGER,
        avg_reward REAL,
        median_reward REAL,
        success_rate REAL,
        failure_rate REAL,
        avg_platform_sc_abs_max REAL,
        avg_turnover REAL,
        avg_fitness REAL,
        performance_json TEXT,
        created_at TEXT,
        raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS strategy_allocations (
        allocation_id TEXT PRIMARY KEY,
        strategy_id TEXT,
        role TEXT,
        budget REAL,
        effective_from TEXT,
        effective_to TEXT,
        reason TEXT,
        created_at TEXT,
        raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS strategy_decisions (
        decision_id TEXT PRIMARY KEY,
        strategy_id TEXT,
        alpha_id TEXT,
        decision_type TEXT,
        selected INTEGER,
        shadow INTEGER,
        score REAL,
        model_version TEXT,
        created_at TEXT,
        raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS offline_replay_reports (
        report_id TEXT PRIMARY KEY,
        task_name TEXT,
        strategy_id TEXT,
        model_version TEXT,
        decision_type TEXT,
        sample_count INTEGER,
        support_coverage REAL,
        model_match_rate REAL,
        estimated_reward_delta REAL,
        estimated_risk_delta REAL,
        replay_pass INTEGER,
        report_json TEXT,
        created_at TEXT,
        raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS policy_replay_evaluations (
        evaluation_id TEXT PRIMARY KEY,
        task_name TEXT,
        model_version TEXT,
        decision_type TEXT,
        sample_count INTEGER,
        support_coverage REAL,
        action_coverage REAL,
        avg_legacy_score REAL,
        avg_model_score REAL,
        estimated_reward_delta REAL,
        estimated_sc_risk_delta REAL,
        estimated_failure_delta REAL,
        evaluation_json TEXT,
        created_at TEXT,
        raw_payload TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS model_safety_reports (
        report_id TEXT PRIMARY KEY,
        task_name TEXT,
        model_version TEXT,
        strategy_id TEXT,
        validation_pass INTEGER,
        replay_pass INTEGER,
        support_pass INTEGER,
        promotion_pass INTEGER,
        safety_status TEXT,
        reason TEXT,
        report_json TEXT,
        created_at TEXT,
        raw_payload TEXT
    );
    """,
)

REFRACTOR_INDEX_DDL: tuple[str, ...] = (
    "CREATE INDEX IF NOT EXISTS idx_ml_training_samples_task ON ml_training_samples(task_name, created_at);",
    "CREATE INDEX IF NOT EXISTS idx_sc_training_samples_alpha ON sc_training_samples(alpha_id, created_at);",
    "CREATE INDEX IF NOT EXISTS idx_decision_snapshots_type ON decision_snapshots(decision_type, created_at);",
    "CREATE INDEX IF NOT EXISTS idx_decision_outcomes_decision ON decision_outcomes(decision_id, created_at);",
    "CREATE INDEX IF NOT EXISTS idx_prediction_audit_task ON ml_prediction_audit(task_name, created_at);",
    "CREATE INDEX IF NOT EXISTS idx_parent_selection_child ON parent_selection_samples(child_alpha_id, created_at);",
    "CREATE INDEX IF NOT EXISTS idx_policy_samples_decision ON policy_training_samples(decision_id, created_at);",
    "CREATE INDEX IF NOT EXISTS idx_simulator_samples_alpha ON simulator_training_samples(alpha_id, created_at);",
    "CREATE INDEX IF NOT EXISTS idx_drift_events_created ON drift_events(created_at);",
    "CREATE INDEX IF NOT EXISTS idx_strategy_registry_role ON strategy_registry(role, status, task_name);",
    "CREATE INDEX IF NOT EXISTS idx_strategy_allocations_strategy ON strategy_allocations(strategy_id, created_at);",
    "CREATE INDEX IF NOT EXISTS idx_strategy_decisions_strategy ON strategy_decisions(strategy_id, created_at);",
    "CREATE INDEX IF NOT EXISTS idx_offline_replay_reports_task ON offline_replay_reports(task_name, decision_type, created_at);",
    "CREATE INDEX IF NOT EXISTS idx_model_safety_reports_strategy ON model_safety_reports(strategy_id, created_at);",
)

COMPAT_COLUMNS: dict[str, dict[str, str]] = {
    "insight_usage": {
        "usage_id": "TEXT",
        "insight_id": "TEXT",
        "alpha_id": "TEXT",
        "prompt_context_json": "TEXT",
        "created_at": "TEXT",
        "raw_payload": "TEXT",
    },
    "insight_effect_samples": {
        "effect_id": "TEXT",
        "insight_id": "TEXT",
        "alpha_id": "TEXT",
        "reward": "REAL",
        "fitness": "REAL",
        "sharpe": "REAL",
        "turnover": "REAL",
        "platform_sc_abs_max": "REAL",
        "created_at": "TEXT",
        "raw_payload": "TEXT",
    },
    "drift_events": {
        "event_id": "TEXT",
        "drift_type": "TEXT",
        "severity": "TEXT",
        "metric_name": "TEXT",
        "event_json": "TEXT",
        "created_at": "TEXT",
        "raw_payload": "TEXT",
    },
    "strategy_registry": {
        "strategy_id": "TEXT",
        "strategy_type": "TEXT",
        "role": "TEXT",
        "task_name": "TEXT",
        "model_version": "TEXT",
        "status": "TEXT",
        "created_at": "TEXT",
        "updated_at": "TEXT",
        "raw_payload": "TEXT",
    },
    "offline_replay_reports": {
        "report_id": "TEXT",
        "task_name": "TEXT",
        "strategy_id": "TEXT",
        "model_version": "TEXT",
        "decision_type": "TEXT",
        "sample_count": "INTEGER",
        "support_coverage": "REAL",
        "model_match_rate": "REAL",
        "estimated_reward_delta": "REAL",
        "estimated_risk_delta": "REAL",
        "replay_pass": "INTEGER",
        "report_json": "TEXT",
        "created_at": "TEXT",
        "raw_payload": "TEXT",
    },
}


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
    return row is not None


def get_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    if not table_exists(conn, table):
        return set()
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(row[1]) for row in rows}


def ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    if not table_exists(conn, table):
        return
    if column not in get_columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def initialize_refactor_tables(conn: sqlite3.Connection) -> None:
    try:
        for statement in REFRACTOR_TABLE_DDL:
            conn.execute(statement)
        for table, columns in COMPAT_COLUMNS.items():
            for column, definition in columns.items():
                ensure_column(conn, table, column, definition)
        for statement in REFRACTOR_INDEX_DDL:
            conn.execute(statement)
    except Exception as exc:
        raise RuntimeError(f"initialize_refactor_tables failed: {exc}") from exc
