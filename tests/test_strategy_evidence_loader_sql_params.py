from __future__ import annotations

import sqlite3
from types import SimpleNamespace

from wq_workflow.data.migrations import initialize_refactor_tables
from wq_workflow.strategy.evidence_loader import StrategyEvidenceLoader


def _seed(db):
    conn = sqlite3.connect(db)
    initialize_refactor_tables(conn)
    conn.execute("INSERT INTO ml_training_samples(sample_id, task_name, raw_payload) VALUES('s1','parent','{}')")
    conn.execute("INSERT INTO ml_model_registry(model_id, task_name, is_active, raw_payload) VALUES('m1','parent',1,'{}')")
    conn.execute("INSERT INTO ml_prediction_audit(prediction_id, task_name, raw_payload) VALUES('p1','parent','{}')")
    conn.commit()
    conn.close()


def test_count_passes_sql_params_for_ml_tables(tmp_path):
    db = tmp_path / "workflow.db"
    _seed(db)
    loader = StrategyEvidenceLoader(db_path=db, config=SimpleNamespace())

    assert loader._count("ml_training_samples", "task_name=?", ("parent",)) == 1
    assert loader._count("ml_model_registry", "task_name=? AND is_active=1", ("parent",)) == 1
    assert loader._count("ml_prediction_audit", "task_name=?", ("parent",)) == 1
    evidence = loader.load_ml_registry_evidence()

    assert any(item.raw_payload["task_name"] == "parent" for item in evidence)
    assert not any("Incorrect number of bindings supplied" in warning for warning in loader.warnings)


def test_limit_query_passes_limit_param_and_missing_table_warns(tmp_path):
    db = tmp_path / "workflow.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE offline_replay_policy_metrics(metric_id TEXT, reason_codes_json TEXT)")
    conn.commit(); conn.close()
    loader = StrategyEvidenceLoader(db_path=db, config=SimpleNamespace(strategy_scoreboard_default_limit=1))

    assert loader._query("SELECT * FROM offline_replay_policy_metrics LIMIT ?", "offline_replay_policy_metrics", (1,)) == []
    assert loader._count("ml_training_samples", "task_name=?", ("missing",)) == 0

    assert any("missing_table:ml_training_samples" == warning for warning in loader.warnings)
    assert not any("Incorrect number of bindings supplied" in warning for warning in loader.warnings)
