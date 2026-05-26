from __future__ import annotations

import sqlite3
from types import SimpleNamespace

from wq_workflow.strategy.evidence_loader import StrategyEvidenceLoader


def test_readonly_missing_db_does_not_create_database(tmp_path):
    db = tmp_path / "missing.db"
    cfg = SimpleNamespace(
        experiment_status_path=str(tmp_path / "missing_experiment.json"),
        offline_replay_status_path=str(tmp_path / "missing_replay.json"),
        counterfactual_status_path=str(tmp_path / "missing_counterfactual.json"),
        governance_status_path=str(tmp_path / "missing_governance.json"),
    )
    loader = StrategyEvidenceLoader(db_path=db, config=cfg, read_only=True)

    assert loader.load_all_evidence() == []
    assert not db.exists()
    assert any(warning.startswith("missing_db:") for warning in loader.warnings)


def test_readonly_does_not_run_schema_initializers(monkeypatch, tmp_path):
    db = tmp_path / "workflow.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE ml_training_samples(sample_id TEXT, task_name TEXT)")
    conn.execute("INSERT INTO ml_training_samples VALUES('s1','x')")
    conn.commit(); conn.close()

    def fail(*args, **kwargs):
        raise AssertionError("schema initializer should not run for read-only evidence loader")

    monkeypatch.setattr("wq_workflow.storage.schema.initialize_schema", fail)
    monkeypatch.setattr("wq_workflow.data.migrations.initialize_refactor_tables", fail)

    loader = StrategyEvidenceLoader(db_path=db, config=SimpleNamespace(), read_only=True)
    assert loader._count("ml_training_samples", "task_name=?", ("x",)) == 1


def test_readonly_locked_db_fails_open(tmp_path):
    db = tmp_path / "workflow.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE ml_training_samples(sample_id TEXT, task_name TEXT)")
    conn.commit()
    conn.execute("BEGIN EXCLUSIVE")
    try:
        loader = StrategyEvidenceLoader(db_path=db, config=SimpleNamespace(), read_only=True)
        assert loader._count("ml_training_samples") == 0
        assert loader.warnings
    finally:
        conn.rollback(); conn.close()
