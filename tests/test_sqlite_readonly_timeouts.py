from __future__ import annotations

import sqlite3
from types import SimpleNamespace

from wq_workflow.dashboard.readonly_sources import DashboardReadonlySources
from wq_workflow.observability.evidence_loader import ExplanationEvidenceLoader
from wq_workflow.observability.source_adapters import BaseSourceAdapter
from wq_workflow.strategy.evidence_loader import StrategyEvidenceLoader


def test_readonly_sqlite_connections_use_one_second_timeout(monkeypatch, tmp_path):
    db = tmp_path / "workflow.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE ml_training_samples(sample_id TEXT)")
    conn.execute("CREATE TABLE observability_metrics(metric_id TEXT, timestamp TEXT)")
    conn.commit(); conn.close()

    real_connect = sqlite3.connect
    calls = []

    def tracking_connect(*args, **kwargs):
        if args and isinstance(args[0], str) and "mode=ro" in args[0]:
            calls.append(kwargs.get("timeout"))
        return real_connect(*args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", tracking_connect)

    StrategyEvidenceLoader(db_path=db, config=SimpleNamespace())._count("ml_training_samples")
    ExplanationEvidenceLoader(config=SimpleNamespace(observability_explanation_recent_limit=1), db_path=db, root=tmp_path)._load_table_rows("observability_metrics", "observability_metrics", "metric", title_field="metric_id", time_field="timestamp")
    BaseSourceAdapter(config=SimpleNamespace(storage_db_path=str(db)), root=tmp_path)._connect_readonly()[0].close()
    DashboardReadonlySources(root=tmp_path, db_path=db).read_db_summary()

    assert calls and all(value == 1.0 for value in calls)


def test_readonly_missing_db_is_not_created(tmp_path):
    db = tmp_path / "missing.db"
    StrategyEvidenceLoader(db_path=db, config=SimpleNamespace())._count("ml_training_samples")
    ExplanationEvidenceLoader(config=SimpleNamespace(), db_path=db, root=tmp_path)._load_table_rows("observability_metrics", "observability_metrics", "metric", title_field="metric_id", time_field="timestamp")
    BaseSourceAdapter(config=SimpleNamespace(storage_db_path=str(db)), root=tmp_path)._connect_readonly()
    DashboardReadonlySources(root=tmp_path, db_path=db).read_db_summary()
    assert not db.exists()
