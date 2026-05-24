import sqlite3

from wq_workflow.data.json_utils import json_dumps_safe
from wq_workflow.learning.ml.availability import get_ml_dependency_status
from wq_workflow.learning.ml.model_registry import ModelRegistry
from wq_workflow.learning.outcome.policy import OutcomeSimulatorPolicy
from wq_workflow.learning.outcome.predictor import OutcomePredictor
from wq_workflow.learning.outcome.trainer import OutcomeTrainer
from wq_workflow.models import WorkflowConfig
from wq_workflow.storage.schema import initialize_schema


def test_simulator_trainer_predictor_never_skips_by_default(tmp_path):
    db = tmp_path / "workflow.db"; conn = sqlite3.connect(db); initialize_schema(conn)
    for i in range(4):
        conn.execute("INSERT OR REPLACE INTO simulator_training_samples (sample_id,alpha_id,features_json,prediction_json,backtest_success,quality_passed,reward,fitness,sharpe,turnover,failure_type,created_at,raw_payload) VALUES (?,?,?,?,?,?,?,?,?,?,?,datetime('now'),?)", (f"s{i}", f"a{i}", json_dumps_safe({"x": i}), "{}", i % 2, i % 2, float(i), 1, 1, 0.1, "", "{}"))
    conn.commit(); conn.close()
    cfg = WorkflowConfig(enable_simulator_model_training=True, simulator_learning_min_samples=2, simulator_model_min_success_recall=0.0)
    reg = ModelRegistry(root=tmp_path, db_path=db)
    res = OutcomeTrainer(db_path=db, model_registry=reg, config=cfg).train()
    pred = OutcomePredictor(model_registry=reg, config=cfg)
    if get_ml_dependency_status().sklearn_model_available:
        assert res["trained"] is True
        assert "skip_risk" in pred.predict({"x": 1})
    else:
        assert res["reason"] == "dependency_unavailable"
    decision = OutcomeSimulatorPolicy(config=WorkflowConfig(enable_simulator_model_skip=False), predictor=pred).evaluate_candidate({"alpha_id":"a"}, features={"x":1})
    assert decision["should_skip"] is False
