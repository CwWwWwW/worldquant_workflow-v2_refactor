import sqlite3
from types import SimpleNamespace
from wq_workflow.app.healthcheck import run_startup_healthcheck


def test_healthcheck_creates_governance_tables(tmp_path):
    cfg=SimpleNamespace(storage_db_path=str(tmp_path/'workflow.db'), healthcheck_audit_path=str(tmp_path/'audit.jsonl'), enable_refactored_pipeline=False, enable_learning_governance=True)
    r=run_startup_healthcheck(cfg, root=tmp_path)
    assert r['ok']
    conn=sqlite3.connect(tmp_path/'workflow.db')
    tables={x[0] for x in conn.execute("select name from sqlite_master where type='table'")}
    assert {'ml_model_events','ml_online_evaluation'} <= tables
