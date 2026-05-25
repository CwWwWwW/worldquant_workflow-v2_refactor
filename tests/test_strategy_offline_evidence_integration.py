import sqlite3

from wq_workflow.data.json_utils import json_dumps_safe
from wq_workflow.data.migrations import initialize_refactor_tables
from wq_workflow.strategy.evidence_loader import StrategyEvidenceLoader


def test_strategy_offline_evidence_integration_replay_and_counterfactual(tmp_path):
    db = tmp_path / "workflow.db"
    conn = sqlite3.connect(db); initialize_refactor_tables(conn)
    conn.execute("INSERT INTO offline_replay_comparisons(comparison_id, replay_run_id, baseline_policy, challenger_policy, decision_type, reward_delta, success_rate_delta, sc_risk_delta, quality_pass_delta, confidence, verdict, created_at, raw_payload) VALUES('cmp1','r1','legacy','model','candidate_acceptance',0.1,0.1,0.0,0.1,'medium','observe','now','{}')")
    conn.execute("INSERT INTO counterfactual_estimates(estimate_id, request_id, decision_id, evidence_count, effective_evidence_count, estimated_reward, estimated_success_rate, estimated_platform_sc_abs_max, estimated_quality_pass_rate, confidence, verdict, risk_flags_json, reason_codes_json, estimated_not_observed, created_at, raw_payload) VALUES('est1','q1','d1',50,50,0.2,0.8,0.8,0.8,'medium','high_risk',?, '[]', 1, 'now', '{}')", (json_dumps_safe(["x"]),))
    conn.commit(); conn.close()
    evidence = StrategyEvidenceLoader(db_path=db).load_all_evidence()
    assert any(e.evidence_type == "replay_comparison" for e in evidence)
    cf = [e for e in evidence if e.evidence_type == "counterfactual_estimate"][0]
    assert "high_risk_estimate" in cf.risk_flags
    assert cf.raw_payload["actual_outcome"] is False
