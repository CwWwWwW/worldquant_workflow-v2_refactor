import sqlite3

from wq_workflow.learning.ml.prediction_audit import PredictionAuditService
from wq_workflow.learning.outcome.policy import OutcomeSimulatorPolicy
from wq_workflow.learning.outcome.sample_store import OutcomeSampleStore
from wq_workflow.models import WorkflowConfig
from wq_workflow.storage.schema import initialize_schema
from wq_workflow.workflow.context import WorkflowContext


class Predictor:
    def predict(self, features):
        return {"score": 0.1, "confidence": 0.8}


def test_simulator_observe_loop(tmp_path):
    db = tmp_path / "workflow.db"
    conn = sqlite3.connect(db); initialize_schema(conn); conn.close()
    config = WorkflowConfig(enable_simulator_model_skip=False)
    result = OutcomeSimulatorPolicy(config=config, predictor=Predictor(), audit_logger=PredictionAuditService(db_path=db)).evaluate_candidate({"alpha_id": "a1"}, features={"x": 1})
    assert result["should_skip"] is False
    wf = WorkflowContext(iteration_id="i1", alpha_id="a1", candidate={"alpha_id": "a1", "features": {"x": 1}}, metrics={"fitness": 1, "sharpe": 2, "turnover": 0.1}, reward=1.0, quality={"passed": True})
    sid = OutcomeSampleStore(db_path=db).record_simulator_outcome(wf.candidate, result["prediction"], wf)
    assert sid
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT COUNT(*) FROM simulator_training_samples").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM ml_prediction_audit WHERE task_name='simulator'").fetchone()[0] == 1
    conn.close()
