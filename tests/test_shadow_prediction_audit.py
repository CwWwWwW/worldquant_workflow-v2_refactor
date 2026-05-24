import sqlite3

from wq_workflow.learning.ml.prediction_audit import PredictionAuditService
from wq_workflow.storage.schema import initialize_schema


def test_shadow_prediction_audit_all_tasks(tmp_path):
    db = tmp_path / "workflow.db"; conn = sqlite3.connect(db); initialize_schema(conn); conn.close()
    audit = PredictionAuditService(db_path=db)
    for task in ("parent", "policy", "simulator", "sc"):
        audit.audit(task_name=task, alpha_id="a", prediction={"score": 1}, final_source="legacy_parent")
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT COUNT(*) FROM ml_prediction_audit").fetchone()[0] == 4
    assert conn.execute("SELECT prediction_json FROM ml_prediction_audit LIMIT 1").fetchone()[0]
    conn.close()
