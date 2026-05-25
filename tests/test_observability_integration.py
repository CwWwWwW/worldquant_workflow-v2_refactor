from __future__ import annotations

import json
import sqlite3
from types import SimpleNamespace

from wq_workflow.data.migrations import initialize_refactor_tables
from wq_workflow.observability.service import ObservabilityService


def test_observability_integration_fake_status_and_db(tmp_path):
    db = tmp_path / "workflow.db"
    conn = sqlite3.connect(db); initialize_refactor_tables(conn); conn.commit(); conn.close()
    status = tmp_path / "runtime/status/strategy_budget_report.json"
    status.parent.mkdir(parents=True)
    status.write_text(json.dumps({"ok": True}), encoding="utf-8")
    cfg = SimpleNamespace(storage_db_path=str(db), observability_metrics_status_path=str(tmp_path / "runtime/status/observability_metrics.json"), observability_auto_collect=False, enable_observability_metrics=True, observability_fail_open=True, strategy_budget_status_path=str(status))
    result = ObservabilityService(config=cfg, root=tmp_path).collect_metrics()
    assert result["ok"] is True
    assert (tmp_path / "runtime/status/observability_metrics.json").exists()
