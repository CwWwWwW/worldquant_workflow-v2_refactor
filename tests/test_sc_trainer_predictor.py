import sqlite3

from wq_workflow.data.repositories import MLRepository
from wq_workflow.learning.ml.availability import get_ml_dependency_status
from wq_workflow.learning.ml.model_registry import ModelRegistry
from wq_workflow.learning.ml.prediction_audit import PredictionAuditService
from wq_workflow.learning.sc.predictor import SCPredictor
from wq_workflow.learning.sc.trainer import SCTrainer
from wq_workflow.models import WorkflowConfig
from wq_workflow.storage.schema import initialize_schema


def _db(tmp_path):
    db = tmp_path / "workflow.db"
    conn = sqlite3.connect(db); initialize_schema(conn); conn.close()
    return db


def test_sc_trainer_fallback_or_trains_and_predicts(tmp_path):
    db = _db(tmp_path)
    repo = MLRepository(db_path=db)
    for i in range(4):
        repo.insert_training_sample("sc", f"s{i}", f"a{i}", {"x": i, "family": "f"}, {"platform_sc_abs_max": 0.1 * i})
    cfg = WorkflowConfig(sc_learning_min_samples=2, sc_model_max_mae=10.0)
    reg = ModelRegistry(root=tmp_path, db_path=db)
    result = SCTrainer(model_registry=reg, config=cfg, repository=repo).train()
    if not get_ml_dependency_status().sklearn_model_available:
        assert result["reason"] == "dependency_unavailable"
        return
    assert result["trained"] is True
    assert result["active"] is True
    pred = SCPredictor(model_registry=reg, audit_logger=PredictionAuditService(db_path=db), config=cfg).predict({"x": 1}, alpha_id="a1")
    assert pred["source"] == "learned_local"
    assert 0.0 <= pred["learned_local_sc"] <= 1.0
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT COUNT(*) FROM ml_prediction_audit WHERE task_name='sc'").fetchone()[0] >= 1
    conn.close()


def test_sc_not_enough_samples(tmp_path):
    db = _db(tmp_path)
    result = SCTrainer(model_registry=ModelRegistry(root=tmp_path, db_path=db), config=WorkflowConfig(sc_learning_min_samples=10), repository=MLRepository(db_path=db)).train()
    assert result["trained"] is False
