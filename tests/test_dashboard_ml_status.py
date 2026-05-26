from __future__ import annotations

import json
import sqlite3

from wq_workflow.dashboard.status_aggregator import DashboardStatusAggregator


def test_dashboard_ml_status_reads_config_counts_without_model_binary(tmp_path):
    (tmp_path / "config.json").write_text(json.dumps({"enable_ml": True, "enable_ml_prediction": True}), encoding="utf-8")
    status_dir = tmp_path / "runtime" / "status"
    status_dir.mkdir(parents=True)
    (status_dir / "ml_status.json").write_text(json.dumps({"active_model_id": "m1", "safety_gate_status": "pass"}), encoding="utf-8")
    db = tmp_path / "runtime" / "db" / "workflow.db"
    db.parent.mkdir(parents=True)
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE ml_model_registry(id TEXT)")
    conn.execute("CREATE TABLE ml_training_samples(id TEXT)")
    conn.execute("CREATE TABLE ml_prediction_audit(id TEXT, created_at TEXT)")
    conn.execute("INSERT INTO ml_model_registry VALUES('m1')")
    conn.execute("INSERT INTO ml_training_samples VALUES('s1')")
    conn.execute("INSERT INTO ml_prediction_audit VALUES('p1','2026-05-26')")
    conn.commit()
    conn.close()
    (tmp_path / "model.bin").write_bytes(b"x" * 1024)

    snapshot = DashboardStatusAggregator(root=tmp_path).build_snapshot()
    assert snapshot.ml.active_model_id == "m1"
    assert snapshot.ml.model_count == 1
    assert snapshot.ml.training_sample_count == 1
    assert snapshot.ml.prediction_count == 1
    assert snapshot.ml.safety_gate_status == "pass"
