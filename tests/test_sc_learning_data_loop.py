import sqlite3

from wq_workflow.learning.sc.policy import SCLearningPolicy
from wq_workflow.learning.sc.sample_store import SCSampleStore
from wq_workflow.models import WorkflowConfig
from wq_workflow.storage.schema import initialize_schema


class NoModel:
    def predict(self, features, alpha_id=""):
        return {"learned_local_sc": 0.1, "confidence": 0.1, "model_version": "v"}


def test_sc_full_data_loop_complete_and_timeout(tmp_path):
    db = tmp_path / "workflow.db"
    conn = sqlite3.connect(db); initialize_schema(conn); conn.close()
    store = SCSampleStore(db_path=db)
    sid = store.record_if_complete(alpha_id="a1", expression="rank(close)", platform_sc={"status": "complete", "abs_max": 0.2, "max": 0.2, "min": -0.1}, features={"operator_count": 1})
    assert sid
    assert store.record_if_complete(alpha_id="a2", platform_sc={"status": "timeout", "abs_max": 0.9}) is None
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT COUNT(*) FROM sc_training_samples").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM ml_training_samples WHERE task_name='sc'").fetchone()[0] == 1
    conn.close()


def test_sc_policy_sources():
    config = WorkflowConfig(enable_sc_model_fallback=False)
    policy = SCLearningPolicy(config=config, predictor=NoModel())
    assert policy.decide(platform_sc={"status": "complete", "abs_max": 0.3})["final_sc_source"] == "platform"
    result = policy.decide(platform_sc={"status": "timeout"}, estimated_self_corr=0.4)
    assert result["final_sc_source"] == "raw_local_proxy"
    assert result["sc_confidence"] == 0.0
