import sqlite3

from wq_workflow.learning.parent.policy import ParentLearningPolicy
from wq_workflow.learning.parent.sample_store import ParentSampleStore
from wq_workflow.models import WorkflowConfig
from wq_workflow.offline.decision_snapshot import DecisionSnapshotLogger
from wq_workflow.storage.schema import initialize_schema
from wq_workflow.workflow.context import WorkflowContext


def test_parent_observe_loop(tmp_path):
    db = tmp_path / "workflow.db"
    conn = sqlite3.connect(db); initialize_schema(conn); conn.close()
    wf = WorkflowContext(iteration_id="i1", alpha_id="c1", candidate={"alpha_id": "c1"}, metrics={}, reward=1.0, quality={"passed": True})
    policy = ParentLearningPolicy(config=WorkflowConfig(), decision_logger=DecisionSnapshotLogger(db_path=db))
    parent, decision_id = policy.select_parent([{"alpha_id": "p1"}], context={"alpha_id": "c1"}, workflow_context=wf, return_decision_id=True)
    assert parent["alpha_id"] == "p1" and decision_id
    sid = ParentSampleStore(db_path=db).record_parent_outcome(parent, wf.candidate, wf)
    assert sid
    assert ParentSampleStore(db_path=db).record_parent_outcome(None, wf.candidate, wf) is None
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT COUNT(*) FROM decision_snapshots").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM parent_selection_samples").fetchone()[0] == 1
    conn.close()
