from __future__ import annotations

import json
import sqlite3
from types import SimpleNamespace

from wq_workflow.data.migrations import initialize_refactor_tables
from wq_workflow.observability.source_adapters import StrategyMetricsAdapter


def test_observability_strategy_reports_and_budget_count_read_only(tmp_path):
    db = tmp_path / "workflow.db"
    conn = sqlite3.connect(db); initialize_refactor_tables(conn)
    conn.execute("INSERT INTO strategy_budget_allocations (allocation_id, plan_id, strategy_id, suggested_ratio) VALUES ('a','p','s',0.25)")
    conn.commit(); conn.close()
    status_dir = tmp_path / "runtime/status"; status_dir.mkdir(parents=True)
    for name in ("strategy_scoreboard.json", "strategy_portfolio_report.json", "strategy_budget_report.json"):
        (status_dir / name).write_text(json.dumps({"ok": True}), encoding="utf-8")
    before = (status_dir / "strategy_budget_report.json").read_text(encoding="utf-8")
    cfg = SimpleNamespace(storage_db_path=str(db), strategy_scoreboard_status_path=str(status_dir / "strategy_scoreboard.json"), strategy_portfolio_status_path=str(status_dir / "strategy_portfolio_report.json"), strategy_budget_status_path=str(status_dir / "strategy_budget_report.json"), observability_status_max_age_seconds=86400)
    result = StrategyMetricsAdapter(config=cfg, root=tmp_path).collect()
    assert any(m["metric_name"] == "strategy.budget_allocation_count" and m["value"] == 1 for m in result["metrics"])
    assert (status_dir / "strategy_budget_report.json").read_text(encoding="utf-8") == before
