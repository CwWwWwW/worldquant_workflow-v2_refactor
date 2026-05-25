from __future__ import annotations

import sqlite3
from types import SimpleNamespace

from wq_workflow.data.migrations import initialize_refactor_tables
from wq_workflow.observability.source_adapters import GovernanceMetricsAdapter


def test_observability_governance_safe_fallback_no_flags_changed(tmp_path):
    db = tmp_path / "workflow.db"
    conn = sqlite3.connect(db); initialize_refactor_tables(conn); conn.commit(); conn.close()
    cfg = SimpleNamespace(storage_db_path=str(db), governance_status_path=str(tmp_path / "missing.json"), enable_learning_governance=True, enable_parent_model_decision=False, observability_status_max_age_seconds=86400)
    before = cfg.enable_parent_model_decision
    result = GovernanceMetricsAdapter(config=cfg, root=tmp_path).collect()
    assert any(m["metric_name"] == "governance.enabled" for m in result["metrics"])
    assert cfg.enable_parent_model_decision is before
