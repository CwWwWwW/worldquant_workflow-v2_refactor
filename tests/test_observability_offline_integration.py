from __future__ import annotations

import json
import sqlite3
from types import SimpleNamespace

from wq_workflow.data.migrations import initialize_refactor_tables
from wq_workflow.observability.source_adapters import OfflineMetricsAdapter


def test_observability_offline_reports_and_tables_read_only(tmp_path):
    db = tmp_path / "workflow.db"
    conn = sqlite3.connect(db); initialize_refactor_tables(conn)
    conn.execute("INSERT INTO decision_snapshots (decision_id) VALUES ('d')")
    conn.commit(); conn.close()
    status_dir = tmp_path / "runtime/status"; status_dir.mkdir(parents=True)
    paths = {}
    for name in ("decision_snapshot_status.json", "offline_replay_report.json", "counterfactual_report.json"):
        p = status_dir / name; p.write_text(json.dumps({"ok": True}), encoding="utf-8"); paths[name] = str(p)
    cfg = SimpleNamespace(storage_db_path=str(db), decision_snapshot_status_path=paths["decision_snapshot_status.json"], offline_replay_status_path=paths["offline_replay_report.json"], counterfactual_status_path=paths["counterfactual_report.json"], observability_status_max_age_seconds=86400)
    result = OfflineMetricsAdapter(config=cfg, root=tmp_path).collect()
    assert any(m["metric_name"] == "offline.decision_snapshot_count" and m["value"] == 1 for m in result["metrics"])
