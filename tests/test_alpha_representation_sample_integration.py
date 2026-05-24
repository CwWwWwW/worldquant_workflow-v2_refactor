import json
import sqlite3

from wq_workflow.alpha.representation.features import build_alpha_representation
from wq_workflow.learning.outcome.sample_store import OutcomeSampleStore
from wq_workflow.learning.parent.sample_store import ParentSampleStore
from wq_workflow.learning.policy.sample_store import PolicySampleStore
from wq_workflow.learning.sc.sample_store import SCSampleStore
from wq_workflow.storage.schema import initialize_schema
from wq_workflow.workflow.context import WorkflowContext


def _init_db(path):
    conn = sqlite3.connect(path)
    initialize_schema(conn)
    conn.close()


def test_sc_sample_store_uses_alpha_representation_features(tmp_path):
    db = tmp_path / "workflow.db"
    _init_db(db)
    rep = build_alpha_representation("ts_rank(close, 20)")
    sid = SCSampleStore(db_path=db).record_if_complete(
        alpha_id="a1",
        expression="ts_rank(close, 20)",
        platform_sc={"status": "complete", "abs_max": 0.2},
        features={"alpha_representation": rep, "estimated_self_corr": 0.1, "sharpe": 1.2},
    )
    assert sid
    conn = sqlite3.connect(db)
    row = conn.execute("SELECT features_json, context_json FROM sc_training_samples WHERE sample_id=?", (sid,)).fetchone()
    conn.close()
    features = json.loads(row[0])
    context = json.loads(row[1])
    assert features["root_operator_hash"] == rep.features["root_operator_hash"]
    assert features["estimated_self_corr"] == 0.1
    assert context["alpha_representation"]["expression_hash"] == rep.expression_hash


def test_parent_sample_store_writes_parent_representation_summary(tmp_path):
    db = tmp_path / "workflow.db"
    _init_db(db)
    wf = WorkflowContext(iteration_id="i1", alpha_id="c1", metrics={"fitness": 1.0}, reward=1.0, quality={"passed": True})
    parent = {"alpha_id": "p1", "expression": "rank(close)", "reward": 0.5, "metrics": {"sharpe": 1.1}}
    child = {"alpha_id": "c1", "expression": "rank(volume)"}
    sid = ParentSampleStore(db_path=db).record_parent_outcome(parent, child, wf)
    assert sid
    conn = sqlite3.connect(db)
    row = conn.execute("SELECT parent_features_json FROM parent_selection_samples WHERE sample_id=?", (sid,)).fetchone()
    conn.close()
    data = json.loads(row[0])
    assert data["alpha_representation"]["root_operator"] == "rank"
    assert data["alpha_representation_features"]["operator_count"] == 1


def test_policy_sample_store_context_contains_expression_hash(tmp_path):
    db = tmp_path / "workflow.db"
    _init_db(db)
    rep = build_alpha_representation("rank(close)")
    wf = WorkflowContext(
        iteration_id="i1",
        alpha_id="a1",
        candidate={"alpha_id": "a1", "expression": "rank(close)"},
        parent={"alpha_id": "p1", "expression": "rank(volume)"},
        alpha_representation=rep,
        quality={"passed": True},
    )
    wf.decisions.append({"decision_id": "d1", "context": {"alpha_id": "a1"}, "available_actions": [{"action_id": "legacy"}], "chosen_action": {"action_id": "legacy"}})
    sid = PolicySampleStore(db_path=db).record_policy_outcome("d1", wf)
    assert sid
    conn = sqlite3.connect(db)
    row = conn.execute("SELECT context_json FROM policy_training_samples WHERE sample_id=?", (sid,)).fetchone()
    conn.close()
    context = json.loads(row[0])
    assert context["candidate_alpha_representation"]["expression_hash"] == rep.expression_hash
    assert context["parent_alpha_representation"]["root_operator"] == "rank"


def test_simulator_sample_store_features_include_representation_features(tmp_path):
    db = tmp_path / "workflow.db"
    _init_db(db)
    wf = WorkflowContext(
        iteration_id="i1",
        alpha_id="a1",
        candidate={"alpha_id": "a1", "expression": "rank(close)", "candidate_source": "mutation", "mutation_type": "field_swap"},
        metrics={"fitness": 1.0, "sharpe": 2.0, "turnover": 0.1},
        reward=1.0,
        quality={"passed": True},
    )
    sid = OutcomeSampleStore(db_path=db).record_simulator_outcome(wf.candidate, {"score": 0.2}, wf)
    assert sid
    conn = sqlite3.connect(db)
    row = conn.execute("SELECT features_json FROM simulator_training_samples WHERE sample_id=?", (sid,)).fetchone()
    conn.close()
    features = json.loads(row[0])
    assert features["operator_count"] == 1
    assert features["candidate_source"] == "mutation"
    assert features["mutation_type"] == "field_swap"
