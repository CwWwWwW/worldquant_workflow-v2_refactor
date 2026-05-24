import json
import sqlite3

from wq_workflow.learning.policy.policy import ActionLearningPolicy
from wq_workflow.learning.policy.sample_store import PolicySampleStore
from wq_workflow.models import WorkflowConfig
from wq_workflow.offline.decision_snapshot import DecisionSnapshotLogger
from wq_workflow.storage.schema import initialize_schema
from wq_workflow.workflow.context import WorkflowContext


def test_policy_observe_loop(tmp_path):
    db = tmp_path / "workflow.db"
    conn = sqlite3.connect(db); initialize_schema(conn); conn.close()
    wf = WorkflowContext(iteration_id="i1", alpha_id="a1", quality={"passed": True}, platform_sc={"abs_max": 0.2})
    legacy = {"action_id": "legacy"}
    chosen, did = ActionLearningPolicy(config=WorkflowConfig(), decision_logger=DecisionSnapshotLogger(db_path=db)).choose_action([legacy], legacy_action=legacy, context={"alpha_id": "a1"}, workflow_context=wf, return_decision_id=True)
    assert chosen == legacy and did
    sid = PolicySampleStore(db_path=db).record_policy_outcome(did, wf)
    assert sid
    conn = sqlite3.connect(db)
    row = conn.execute("SELECT available_actions_json FROM decision_snapshots WHERE decision_id=?", (did,)).fetchone()
    assert json.loads(row[0])[0]["action_id"] == "legacy"
    assert conn.execute("SELECT COUNT(*) FROM policy_training_samples").fetchone()[0] == 1
    conn.close()
