from __future__ import annotations

import json
import sqlite3

from wq_workflow.dashboard.status_aggregator import DashboardStatusAggregator


def test_dashboard_integration_fake_sources_no_writes(tmp_path):
    status_dir = tmp_path / "runtime" / "status"
    status_dir.mkdir(parents=True)
    target = status_dir / "offline_replay_report.json"
    target.write_text(json.dumps({"runs": [{"id": 1}], "warnings": []}), encoding="utf-8")
    before = target.read_text(encoding="utf-8")
    db = tmp_path / "runtime" / "db" / "workflow.db"
    db.parent.mkdir(parents=True)
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE counterfactual_estimates(id TEXT)")
    conn.execute("INSERT INTO counterfactual_estimates VALUES('c1')")
    conn.commit()
    conn.close()
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "workflow_state.jsonl").write_text("WAIT_RESULT alpha_id=a1", encoding="utf-8")

    snapshot = DashboardStatusAggregator(root=tmp_path).build_snapshot()
    assert snapshot.runtime.current_state == "WAIT_RESULT"
    assert any(status.source == "workflow_db" and status.available for status in snapshot.sources)
    assert snapshot.global_warnings
    assert target.read_text(encoding="utf-8") == before
