import sqlite3

from wq_workflow.learning.ml.prediction_audit import PredictionAuditWriter
from wq_workflow.storage.schema import initialize_schema


def test_prediction_audit_writer_inserts_json_payload(tmp_path):
    db = tmp_path / "workflow.db"
    conn = sqlite3.connect(db)
    initialize_schema(conn)
    writer = PredictionAuditWriter(conn)
    prediction_id = writer.audit_prediction(
        task_name="sc",
        alpha_id="a1",
        model_version="v1",
        features={"x": 1},
        prediction={"score": 0.2},
        confidence=0.7,
        final_decision="shadow",
        final_source="learned",
        raw_payload={"extra": object()},
    )
    assert prediction_id
    row = conn.execute("SELECT task_name, features_json, prediction_json FROM ml_prediction_audit WHERE prediction_id=?", (prediction_id,)).fetchone()
    assert row[0] == "sc"
    assert '"x": 1' in row[1]
    assert '"score": 0.2' in row[2]
    conn.close()


def test_prediction_audit_writer_failure_does_not_raise():
    conn = sqlite3.connect(":memory:")
    writer = PredictionAuditWriter(conn)
    assert writer.audit_prediction(task_name="sc", alpha_id=None) is None
    conn.close()
