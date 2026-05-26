from __future__ import annotations

import sqlite3

from wq_workflow.strategy.evidence_loader import StrategyEvidenceLoader


def _empty_db(path):
    conn = sqlite3.connect(path)
    conn.commit()
    conn.close()


def test_same_missing_table_warns_once(tmp_path):
    db = tmp_path / "workflow.db"
    _empty_db(db)
    loader = StrategyEvidenceLoader(db_path=db)
    assert loader._count("ml_training_samples") == 0
    assert loader._count("ml_training_samples") == 0
    assert loader.warnings.count("missing_table:ml_training_samples") == 1


def test_different_missing_tables_warn_separately(tmp_path):
    db = tmp_path / "workflow.db"
    _empty_db(db)
    loader = StrategyEvidenceLoader(db_path=db)
    loader._count("ml_training_samples")
    loader._count("ml_model_registry")
    assert "missing_table:ml_training_samples" in loader.warnings
    assert "missing_table:ml_model_registry" in loader.warnings


def test_same_missing_status_warns_once(tmp_path):
    loader = StrategyEvidenceLoader(root_dir=tmp_path)
    loader._read_status_json("runtime/status/missing.json")
    loader._read_status_json("runtime/status/missing.json")
    assert loader.warnings.count("missing_status:missing") == 1


def test_query_failed_same_error_type_warns_once(tmp_path):
    db = tmp_path / "workflow.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE offline_replay_policy_metrics(metric_id TEXT)")
    conn.commit()
    conn.close()
    loader = StrategyEvidenceLoader(db_path=db)
    loader._query("SELECT missing_column FROM offline_replay_policy_metrics", "offline_replay_policy_metrics")
    loader._query("SELECT missing_column FROM offline_replay_policy_metrics", "offline_replay_policy_metrics")
    warnings = [w for w in loader.warnings if w.startswith("query_failed:offline_replay_policy_metrics:")]
    assert len(warnings) == 1


def test_different_query_failed_sources_are_not_dropped(tmp_path):
    db = tmp_path / "workflow.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE offline_replay_policy_metrics(metric_id TEXT)")
    conn.execute("CREATE TABLE counterfactual_estimates(estimate_id TEXT)")
    conn.commit()
    conn.close()
    loader = StrategyEvidenceLoader(db_path=db)
    loader._query("SELECT missing_column FROM offline_replay_policy_metrics", "offline_replay_policy_metrics")
    loader._query("SELECT missing_column FROM counterfactual_estimates", "counterfactual_estimates")
    assert any(w.startswith("query_failed:offline_replay_policy_metrics:") for w in loader.warnings)
    assert any(w.startswith("query_failed:counterfactual_estimates:") for w in loader.warnings)


def test_warning_cap_still_applies():
    loader = StrategyEvidenceLoader()
    for index in range(105):
        loader._warn(f"warning:{index}")
    assert len(loader.warnings) == 100
    assert loader.warnings[0] == "warning:5"
