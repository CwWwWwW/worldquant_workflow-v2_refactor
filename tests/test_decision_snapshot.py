import json
import sqlite3

from wq_workflow.offline.decision_snapshot import DecisionSnapshotLogger
from wq_workflow.storage.schema import initialize_schema


def test_decision_snapshot_records_actions(tmp_path):
    db_path = tmp_path / "workflow.db"
    conn = sqlite3.connect(db_path)
    initialize_schema(conn)
    conn.close()
    logger = DecisionSnapshotLogger(db_path=db_path)
    decision_id = logger.record(decision_type="parent", alpha_id="a1", available_actions=[{"id": "p1"}], chosen_action={"id": "p1"}, action_scores={"p1": 1.0})
    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT available_actions_json, chosen_action_json, action_scores_json, model_version FROM decision_snapshots WHERE decision_id=?", (decision_id,)).fetchone()
    conn.close()
    assert json.loads(row[0])[0]["id"] == "p1"
    assert json.loads(row[1])["id"] == "p1"
    assert json.loads(row[2])["p1"] == 1.0
    assert row[3] == ""
