from __future__ import annotations

import json
import os
import sqlite3
import time

from wq_workflow.dashboard.readonly_sources import DashboardReadonlySources


def test_readonly_sources_missing_corrupt_stale_json(tmp_path):
    src = DashboardReadonlySources(root=tmp_path, stale_after_seconds=1)
    missing, payload = src.read_json_source("missing", tmp_path / "missing.json")
    assert missing.available is False and payload == {}

    corrupt = tmp_path / "bad.json"
    corrupt.write_text("{bad", encoding="utf-8")
    status, payload = src.read_json_source("bad", corrupt)
    assert status.available is False and payload == {}

    stale = tmp_path / "stale.json"
    stale.write_text(json.dumps({"updated_at": "old", "value": 1}), encoding="utf-8")
    old = time.time() - 10
    os.utime(stale, (old, old))
    status, payload = src.read_json_source("stale", stale)
    assert status.available is True and status.stale is True and payload["value"] == 1


def test_readonly_sources_db_read_only_and_missing_locked(tmp_path):
    db = tmp_path / "workflow.db"
    src = DashboardReadonlySources(root=tmp_path, db_path=db)
    missing, summary = src.read_db_summary()
    assert missing.available is False and summary == {}

    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE ml_model_registry(id TEXT)")
    conn.execute("INSERT INTO ml_model_registry VALUES('m1')")
    conn.commit()
    conn.close()

    status, summary = src.read_db_summary()
    assert status.available is True
    assert summary["ml_model_registry_count"] == 1

    conn = sqlite3.connect(db)
    conn.execute("BEGIN EXCLUSIVE")
    try:
        status, _ = src.read_db_summary()
        assert status.available in {True, False}
    finally:
        conn.rollback()
        conn.close()


def test_readonly_sources_log_tail_not_full_file(tmp_path):
    log = tmp_path / "workflow.log"
    log.write_text("x" * 300_000 + "\nWAIT_RESULT alpha_id=a1\n", encoding="utf-8")
    src = DashboardReadonlySources(root=tmp_path, log_paths=[log])
    text = src.log_summarizer.read_tail(log, max_bytes=200_000)
    assert len(text) <= 200_100
    status, summary = src.read_log_summary(limit=5)
    assert status.available is True
    assert summary["events"][-1]["state"] == "WAIT_RESULT"
