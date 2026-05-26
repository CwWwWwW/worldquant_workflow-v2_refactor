from __future__ import annotations

import json
import sqlite3

from wq_workflow.dashboard.status_aggregator import DashboardStatusAggregator


def _write_status(tmp_path, name, payload):
    status_dir = tmp_path / "runtime" / "status"
    status_dir.mkdir(parents=True, exist_ok=True)
    (status_dir / name).write_text(json.dumps(payload), encoding="utf-8")


def test_status_aggregator_combines_strategy_observability_ml_runtime(tmp_path):
    _write_status(tmp_path, "strategy_portfolio_report.json", {"strategy_states": [{"strategy_id": "s1", "current_state": "champion"}, {"strategy_id": "s2", "current_state": "challenger"}]})
    _write_status(tmp_path, "strategy_budget_report.json", {"allocations": [{"strategy_id": "s1", "suggested_ratio": 0.7}, {"strategy_id": "s2", "suggested_ratio": 0.3}]})
    _write_status(tmp_path, "observability_metrics.json", {"updated_at": "now"})
    _write_status(tmp_path, "observability_alerts.json", {"alert_count": 2, "critical_count": 1, "warning_count": 1})
    _write_status(tmp_path, "health_diagnosis.json", {"overall_status": "warning"})
    _write_status(tmp_path, "run_explain_report.json", {"key_findings": ["counterfactual evidence is estimated"], "recommended_human_checks": ["review"]})
    _write_status(tmp_path, "stage7_summary_report.json", {"stage_name": "phase7-observability"})
    _write_status(tmp_path, "ml_status.json", {"active_model_id": "m1", "prediction_count": 4})
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "workflow_state.jsonl").write_text(json.dumps({"time": "t", "state": "PARSE_RESULT", "alpha_id": "a1", "template_file": "tpl", "iteration": 3}), encoding="utf-8")
    db = tmp_path / "runtime" / "db" / "workflow.db"
    db.parent.mkdir(parents=True)
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE ml_model_registry(id TEXT)")
    conn.execute("CREATE TABLE ml_training_samples(id TEXT)")
    conn.execute("INSERT INTO ml_model_registry VALUES('m1')")
    conn.commit()
    conn.close()

    snapshot = DashboardStatusAggregator(root=tmp_path).build_snapshot()
    assert snapshot.runtime.current_state == "PARSE_RESULT"
    assert snapshot.runtime.current_alpha_id == "a1"
    assert snapshot.strategy.champion == "s1"
    assert snapshot.strategy.budget_total_ratio == 1.0
    assert snapshot.ml.active_model_id == "m1"
    assert snapshot.ml.model_count == 1
    assert snapshot.observability.alert_count == 2
    assert snapshot.observability.key_findings


def test_status_aggregator_source_failure_is_warning(tmp_path):
    _write_status(tmp_path, "observability_metrics.json", {"ok": True})
    snapshot = DashboardStatusAggregator(root=tmp_path, include_db=False, include_logs=False).build_snapshot()
    assert snapshot.sources
    assert any("missing" in warning for warning in snapshot.global_warnings)
