import sqlite3
from types import SimpleNamespace

from wq_workflow.data.migrations import initialize_refactor_tables
from wq_workflow.strategy.service import StrategyService


def test_strategy_integration_generates_scoreboard_from_fake_evidence(tmp_path):
    db = tmp_path / "workflow.db"
    conn = sqlite3.connect(db); initialize_refactor_tables(conn)
    conn.execute("INSERT INTO offline_replay_policy_metrics(metric_id, replay_run_id, policy_name, decision_type, sample_count, observable_count, avg_reward, success_rate, avg_platform_sc_abs_max, quality_pass_rate, reason_codes_json, raw_payload) VALUES('m1','r1','legacy','candidate_acceptance',120,120,0.1,0.7,0.2,0.9,'[]','{}')")
    conn.execute("INSERT INTO counterfactual_summaries(summary_id, decision_type, request_count, estimate_count, insufficient_count, high_risk_count, medium_or_high_confidence_count, avg_evidence_count, updated_at, raw_payload) VALUES('s1','candidate_acceptance',1,120,0,0,120,30,'now','{}')")
    conn.commit(); conn.close()
    cfg = SimpleNamespace(enable_strategy_registry=True, strategy_scoreboard_status_path=str(tmp_path / "status.json"), strategy_registry_mode="advisory", strategy_scoreboard_auto_refresh=False, strategy_fail_open=True, storage_db_path=str(db))
    svc = StrategyService(config=cfg, db_path=db)
    assert svc.refresh_scoreboard()["ok"] is True
    assert (tmp_path / "status.json").exists()
    assert any(score.strategy_id == "replay_supported_policy" for score in svc.list_strategy_scores())
