import json
import sqlite3

from wq_workflow.data.repositories import DecisionRepository, DriftRepository, MLRepository
from wq_workflow.storage.schema import initialize_schema


def _conn(path):
    conn = sqlite3.connect(path)
    initialize_schema(conn)
    return conn


def test_ml_repository_training_and_prediction_audit(tmp_path):
    db = tmp_path / "workflow.db"
    repo = MLRepository(db_path=db)
    repo.insert_training_sample("sc", "s1", "a1", {"x": 1}, {"y": 2}, {"c": 3}, {"raw": True})
    rows = repo.load_training_samples("sc")
    assert rows[0]["features"]["x"] == 1
    repo.audit_prediction("sc", "p1", "a1", "v1", {"x": 1}, {"pred": 0.2}, 0.9, "use", "model", {})
    conn = _conn(db)
    assert conn.execute("SELECT COUNT(*) FROM ml_prediction_audit WHERE task_name='sc'").fetchone()[0] == 1
    conn.close()


def test_decision_repository_snapshot_and_outcome(tmp_path):
    db = tmp_path / "workflow.db"
    repo = DecisionRepository(db_path=db)
    did = repo.insert_decision_snapshot(decision_type="policy", alpha_id="a1", available_actions=[{"a": 1}], chosen_action={"a": 1})
    repo.insert_decision_outcome(decision_id=did, decision_type="policy", alpha_id="a1", reward=1.2, success=True, metrics={"fitness": 1})
    conn = _conn(db)
    row = conn.execute("SELECT available_actions_json FROM decision_snapshots WHERE decision_id=?", (did,)).fetchone()
    assert json.loads(row[0])[0]["a"] == 1
    assert conn.execute("SELECT COUNT(*) FROM decision_outcomes WHERE decision_id=?", (did,)).fetchone()[0] == 1
    conn.close()


def test_drift_repository_insert(tmp_path):
    repo = DriftRepository(db_path=tmp_path / "workflow.db")
    event_id = repo.insert_drift_event({"drift_type": "reward", "severity": "low", "event": {"x": 1}})
    assert repo.list_recent_events()[0]["event_id"] == event_id
