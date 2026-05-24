import sqlite3

from wq_workflow.learning.sc.policy import SCLearningPolicy
from wq_workflow.learning.sc.predictor import SCPredictor
from wq_workflow.learning.sc.sample_store import SCSampleStore
from wq_workflow.models import WorkflowConfig
from wq_workflow.storage.schema import initialize_schema


class EmptyRegistry:
    def load_active_model(self, task_name):
        return None


def test_sc_sample_store_complete_only(tmp_path):
    db_path = tmp_path / "workflow.db"
    conn = sqlite3.connect(db_path)
    initialize_schema(conn)
    conn.close()
    store = SCSampleStore(db_path=db_path)

    sample_id = store.record_sample(alpha_id="a1", expression="ts_rank(close,20)", platform_sc={"status": "complete", "abs_max": 0.33}, features={"operator_count": 1})
    assert sample_id
    assert store.record_sample(alpha_id="a2", platform_sc={"status": "timeout", "abs_max": 0.9}) is None

    conn = sqlite3.connect(db_path)
    assert conn.execute("SELECT COUNT(*) FROM sc_training_samples").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM ml_training_samples WHERE task_name='sc'").fetchone()[0] == 1
    conn.close()


def test_sc_policy_platform_priority_and_no_default_fallback():
    config = WorkflowConfig(enable_sc_model_fallback=False)
    predictor = SCPredictor(model_registry=EmptyRegistry(), config=config)
    policy = SCLearningPolicy(config=config, predictor=predictor)
    assert policy.decide(platform_sc={"status": "complete", "abs_max": 0.42}, estimated_self_corr=0.8)["final_sc_source"] == "platform"
    result = policy.decide(platform_sc={"status": "timeout"}, estimated_self_corr=0.21, features={"x": 1})
    assert result["final_sc_source"] == "raw_local_proxy"
    assert result["final_sc"] == 0.21
    assert predictor.predict({"x": 1})["source"] == "no_active_model"
