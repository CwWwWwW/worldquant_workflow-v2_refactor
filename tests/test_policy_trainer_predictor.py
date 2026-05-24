import sqlite3

from wq_workflow.data.json_utils import json_dumps_safe
from wq_workflow.learning.ml.availability import get_ml_dependency_status
from wq_workflow.learning.ml.model_registry import ModelRegistry
from wq_workflow.learning.policy.policy import ActionLearningPolicy
from wq_workflow.learning.policy.predictor import PolicyPredictor
from wq_workflow.learning.policy.trainer import PolicyTrainer
from wq_workflow.models import WorkflowConfig
from wq_workflow.storage.schema import initialize_schema


def test_policy_trainer_predictor_shadow_legacy(tmp_path):
    db = tmp_path / "workflow.db"; conn = sqlite3.connect(db); initialize_schema(conn)
    for i in range(4):
        conn.execute("INSERT OR REPLACE INTO policy_training_samples (sample_id,decision_id,alpha_id,context_json,available_actions_json,chosen_action_json,reward_delta,success,failure_type,platform_sc_abs_max,created_at,raw_payload) VALUES (?,?,?,?,?,?,?,?,?,?,datetime('now'),?)", (f"s{i}", f"d{i}", f"a{i}", json_dumps_safe({"ctx": i}), json_dumps_safe([{"action_id":"unused"}]), json_dumps_safe({"action_id": f"act{i%2}", "legacy_score": i}), float(i), i % 2, "", 0.1, "{}"))
    conn.commit(); conn.close()
    cfg = WorkflowConfig(enable_policy_model_training=True, policy_learning_min_samples=2, policy_model_max_mae=10.0, policy_min_action_coverage=0.0)
    reg = ModelRegistry(root=tmp_path, db_path=db)
    res = PolicyTrainer(db_path=db, model_registry=reg, config=cfg).train()
    if get_ml_dependency_status().sklearn_model_available:
        assert res["trained"] is True
        scored = PolicyPredictor(model_registry=reg, config=cfg).score_actions([{"action_id": "a", "legacy_score": 1}], context={"ctx": 1})
        assert "action_score" in scored[0]
    else:
        assert res["reason"] == "dependency_unavailable"
    legacy = {"action_id": "legacy"}
    chosen = ActionLearningPolicy(config=WorkflowConfig(enable_policy_model_decision=False), predictor=PolicyPredictor(model_registry=reg, config=cfg)).choose_action([legacy], legacy_action=legacy)
    assert chosen == legacy
