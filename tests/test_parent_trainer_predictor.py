import sqlite3

from wq_workflow.data.json_utils import json_dumps_safe
from wq_workflow.learning.ml.availability import get_ml_dependency_status
from wq_workflow.learning.ml.model_registry import ModelRegistry
from wq_workflow.learning.ml.prediction_audit import PredictionAuditService
from wq_workflow.learning.parent.policy import ParentLearningPolicy
from wq_workflow.learning.parent.predictor import ParentPredictor
from wq_workflow.learning.parent.trainer import ParentTrainer
from wq_workflow.models import WorkflowConfig
from wq_workflow.storage.schema import initialize_schema


def test_parent_trainer_predictor_shadow_legacy(tmp_path):
    db = tmp_path / "workflow.db"; conn = sqlite3.connect(db); initialize_schema(conn)
    for i in range(4):
        conn.execute("INSERT OR REPLACE INTO parent_selection_samples (sample_id,parent_alpha_id,child_alpha_id,parent_features_json,child_metrics_json,child_reward,reward_delta,child_success,child_platform_sc_abs_max,mutation_type,created_at,raw_payload) VALUES (?,?,?,?,?,?,?,?,?,?,datetime('now'),?)", (f"p{i}", f"p{i}", f"c{i}", json_dumps_safe({"parent_reward": i, "mutation_type": "m"}), "{}", float(i), 0.1, i % 2, 0.2, "m", "{}"))
    conn.commit(); conn.close()
    cfg = WorkflowConfig(enable_parent_model_training=True, parent_learning_min_samples=2, parent_model_max_mae=10.0)
    reg = ModelRegistry(root=tmp_path, db_path=db)
    res = ParentTrainer(db_path=db, model_registry=reg, config=cfg).train()
    if get_ml_dependency_status().sklearn_model_available:
        assert res["trained"] is True
        pred = ParentPredictor(model_registry=reg, audit_logger=PredictionAuditService(db_path=db), config=cfg)
        ranked = pred.rank_parents([{"alpha_id": "p1", "parent_reward": 1}], alpha_id="a")
        assert "parent_rank_score" in ranked[0]
    else:
        assert res["reason"] == "dependency_unavailable"
    chosen = ParentLearningPolicy(config=WorkflowConfig(enable_parent_model_decision=False), predictor=ParentPredictor(model_registry=reg, config=cfg)).select_parent([{"alpha_id": "legacy"}], context={"alpha_id": "a"})
    assert chosen["alpha_id"] == "legacy"
