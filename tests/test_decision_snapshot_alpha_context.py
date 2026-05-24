import json
import sqlite3

from wq_workflow.offline.decision_snapshot import DecisionSnapshotLogger
from wq_workflow.storage.schema import initialize_schema


def _init_db(path):
    conn = sqlite3.connect(path)
    initialize_schema(conn)
    conn.close()


def test_decision_snapshot_context_auto_contains_alpha_summary(tmp_path):
    db = tmp_path / "workflow.db"
    _init_db(db)
    did = DecisionSnapshotLogger(db_path=db).record(
        decision_type="policy_action",
        alpha_id="a1",
        context={"expression": "rank(close)"},
        available_actions=[{"id": "a"}],
        chosen_action={"id": "a"},
    )
    conn = sqlite3.connect(db)
    row = conn.execute("SELECT context_json FROM decision_snapshots WHERE decision_id=?", (did,)).fetchone()
    conn.close()
    context = json.loads(row[0])
    assert context["alpha_representation"]["root_operator"] == "rank"
    assert "ast" not in context["alpha_representation"]


def test_decision_snapshot_parse_failure_writes_failed_summary(tmp_path):
    db = tmp_path / "workflow.db"
    _init_db(db)
    did = DecisionSnapshotLogger(db_path=db).record(decision_type="parent", alpha_id="a1", context={"expression": "rank(close"})
    conn = sqlite3.connect(db)
    row = conn.execute("SELECT context_json FROM decision_snapshots WHERE decision_id=?", (did,)).fetchone()
    conn.close()
    context = json.loads(row[0])
    assert context["alpha_representation"]["parse_status"] == "failed"
