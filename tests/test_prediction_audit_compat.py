import sqlite3

from wq_workflow.learning.ml.prediction_audit import PredictionAuditService, safe_audit_prediction
from wq_workflow.learning.sc.predictor import SCPredictor
from wq_workflow.storage.schema import initialize_schema


class RecordOnly:
    def __init__(self):
        self.called = False

    def record(self, **kwargs):
        self.called = True
        return "record-id"


class AuditOnly:
    def __init__(self):
        self.called = False

    def audit(self, **kwargs):
        self.called = True
        return "audit-id"


class RaisingAudit:
    def record(self, **kwargs):
        raise RuntimeError("audit boom")


class Schema:
    def transform_one(self, features):
        return [float(features.get("x", 0.0))]


class Model:
    def predict(self, rows):
        return [0.42]


class Registry:
    def load_active_model(self, task):
        return {"model": Model(), "feature_schema": Schema(), "model_version": "v1"}


def test_prediction_audit_service_audit_and_record(tmp_path):
    db = tmp_path / "workflow.db"
    conn = sqlite3.connect(db)
    initialize_schema(conn)
    conn.close()
    service = PredictionAuditService(db_path=db)
    assert service.audit(task_name="sc", alpha_id="a1", prediction={"x": 1})
    assert service.record(task_name="sc", alpha_id="a2", prediction={"x": 2})


def test_safe_audit_prediction_supports_record_and_audit_objects():
    record = RecordOnly()
    audit = AuditOnly()
    assert safe_audit_prediction(record, task_name="sc") == "record-id"
    assert record.called is True
    assert safe_audit_prediction(audit, task_name="sc") == "audit-id"
    assert audit.called is True


def test_safe_audit_prediction_swallows_audit_exceptions():
    assert safe_audit_prediction(RaisingAudit(), task_name="sc") is None


def test_sc_predictor_audit_failure_does_not_change_prediction():
    pred = SCPredictor(model_registry=Registry(), audit_logger=RaisingAudit()).predict({"x": 1}, alpha_id="a1")
    assert pred["source"] == "learned_local"
    assert pred["learned_local_sc"] == 0.42
