import sqlite3
from wq_workflow.data.migrations import initialize_refactor_tables


def test_governance_migrations_idempotent_and_legacy_meta_kept(tmp_path):
    conn=sqlite3.connect(tmp_path/'db.sqlite')
    conn.execute('create table if not exists evolution_meta (key TEXT PRIMARY KEY, value TEXT, updated_at TEXT)')
    conn.execute('insert or replace into evolution_meta(key,value) values(?,?)',('legacy_full_import_completed','true'))
    initialize_refactor_tables(conn); initialize_refactor_tables(conn)
    tables={x[0] for x in conn.execute("select name from sqlite_master where type='table'")}
    assert {'ml_model_events','ml_online_evaluation'} <= tables
    assert conn.execute('select value from evolution_meta where key=?',('legacy_full_import_completed',)).fetchone()[0] == 'true'
