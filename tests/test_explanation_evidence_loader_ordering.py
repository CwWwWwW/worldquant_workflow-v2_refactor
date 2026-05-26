from __future__ import annotations

import sqlite3
from types import SimpleNamespace

from wq_workflow.observability.evidence_loader import ExplanationEvidenceLoader


def test_time_field_is_used_when_available(tmp_path):
    db = tmp_path / "workflow.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE observability_metrics(metric_id TEXT, timestamp TEXT)")
    conn.execute("INSERT INTO observability_metrics VALUES('old','2026-01-01')")
    conn.execute("INSERT INTO observability_metrics VALUES('new','2026-01-02')")
    conn.commit(); conn.close()

    loader = ExplanationEvidenceLoader(config=SimpleNamespace(observability_explanation_recent_limit=2), db_path=db, root=tmp_path)
    rows = loader._load_table_rows("observability_metrics", "observability_metrics", "metric", title_field="metric_id", time_field="timestamp")
    assert [row.title for row in rows] == ["new", "old"]


def test_order_fallback_is_deterministic_and_rowid_failure_fails_open(tmp_path):
    db = tmp_path / "workflow.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE no_rowid_table(id TEXT PRIMARY KEY, value TEXT) WITHOUT ROWID")
    conn.execute("INSERT INTO no_rowid_table VALUES('b','2')")
    conn.execute("INSERT INTO no_rowid_table VALUES('a','1')")
    conn.commit(); conn.close()

    loader = ExplanationEvidenceLoader(config=SimpleNamespace(observability_explanation_recent_limit=10), db_path=db, root=tmp_path)
    assert loader._pick_order_field({"id", "value"}, "missing_time") == "rowid"
    rows = loader._load_table_rows("no_rowid_table", "system", "text", title_field="id", time_field="missing_time")

    assert {row.title for row in rows} == {"a", "b"}
    assert any(warning.startswith("order_fallback:no_rowid_table:rowid:") for warning in loader.warnings)
