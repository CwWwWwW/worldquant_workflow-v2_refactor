import sqlite3
from types import SimpleNamespace

from wq_workflow.data.migrations import initialize_refactor_tables
from wq_workflow.data.json_utils import json_dumps_safe
from wq_workflow.strategy.evidence_loader import StrategyEvidenceLoader


def test_strategy_evidence_loader_empty_and_sources(tmp_path):
    db = tmp_path / "workflow.db"
    conn = sqlite3.connect(db); conn.row_factory = sqlite3.Row
    initialize_refactor_tables(conn)
    conn.execute("INSERT INTO offline_replay_policy_metrics(metric_id, replay_run_id, policy_name, decision_type, sample_count, observable_count, avg_reward, success_rate, avg_platform_sc_abs_max, quality_pass_rate, reason_codes_json, raw_payload) VALUES('m1','r1','legacy','candidate_acceptance',40,40,0.1,0.6,0.2,0.7,'[]','{}')")
    conn.execute("INSERT INTO counterfactual_estimates(estimate_id, request_id, decision_id, evidence_count, effective_evidence_count, estimated_reward, estimated_success_rate, estimated_platform_sc_abs_max, estimated_quality_pass_rate, confidence, verdict, risk_flags_json, reason_codes_json, estimated_not_observed, created_at, raw_payload) VALUES('c1','q1','d1',40,40,0.2,0.6,0.3,0.8,'medium','ok',?, '[]', 1, 'now', '{}')", (json_dumps_safe(["x"]),))
    conn.execute("INSERT INTO model_safety_reports(report_id, strategy_id, safety_status, reason, created_at, raw_payload) VALUES('g1','s1','fail','blocked','now','{}')")
    conn.commit(); conn.close()
    loader = StrategyEvidenceLoader(db_path=db, config=SimpleNamespace())
    evidence = loader.load_all_evidence()
    assert any(e.evidence_type == "replay_metrics" for e in evidence)
    cf = [e for e in evidence if e.evidence_type == "counterfactual_estimate"][0]
    assert "counterfactual_estimated_not_actual" in cf.reason_codes
    assert cf.raw_payload["actual_outcome"] is False
    assert any("governance_blocked" in e.risk_flags for e in evidence)
    empty_cfg = SimpleNamespace(
        experiment_status_path=str(tmp_path / "missing_experiment.json"),
        offline_replay_status_path=str(tmp_path / "missing_replay.json"),
        counterfactual_status_path=str(tmp_path / "missing_counterfactual.json"),
        governance_status_path=str(tmp_path / "missing_governance.json"),
    )
    assert StrategyEvidenceLoader(db_path=tmp_path / "empty.db", config=empty_cfg).load_all_evidence() == []
