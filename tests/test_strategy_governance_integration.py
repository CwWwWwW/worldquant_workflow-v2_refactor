import sqlite3
from types import SimpleNamespace

from wq_workflow.data.migrations import initialize_refactor_tables
from wq_workflow.strategy.evidence_loader import StrategyEvidenceLoader
from wq_workflow.strategy.scorer import StrategyScorer
from wq_workflow.strategy.schema import StrategyProfile


def test_strategy_governance_integration_blocked_is_risk_only(tmp_path):
    db = tmp_path / "workflow.db"
    conn = sqlite3.connect(db); initialize_refactor_tables(conn)
    conn.execute("INSERT INTO model_safety_reports(report_id, strategy_id, safety_status, reason, created_at, raw_payload) VALUES('r1','ml_parent_policy','fail','blocked','now','{}')")
    conn.commit(); conn.close()
    evidence = StrategyEvidenceLoader(db_path=db, config=SimpleNamespace()).load_governance_evidence()
    assert any("governance_blocked" in e.risk_flags for e in evidence)
    score = StrategyScorer(SimpleNamespace()).score_strategy(StrategyProfile(strategy_id="governance_safe_policy", strategy_type="governance_safe_policy"), evidence)
    assert score.recommendation == "blocked_by_governance"
    row = sqlite3.connect(db).execute("SELECT safety_status FROM model_safety_reports WHERE report_id='r1'").fetchone()
    assert row[0] == "fail"
