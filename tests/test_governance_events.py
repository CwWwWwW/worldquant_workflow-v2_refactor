import sqlite3, json
from wq_workflow.governance.events import ModelEventLogger


def test_event_record_writes_and_json_safe(tmp_path):
    conn = sqlite3.connect(tmp_path/'db.sqlite')
    logger = ModelEventLogger(conn=conn)
    ev = logger.record(task_name='sc', model_version='v1', event_type='model_disabled', raw_payload={'bad': object()})
    row = conn.execute('select event_type, raw_payload from ml_model_events').fetchone()
    assert row[0] == 'model_disabled'
    json.loads(row[1])
    assert ev['event_id']


def test_event_db_error_not_raised(tmp_path):
    class Bad:
        def execute(self,*a,**k): raise RuntimeError('bad')
        def commit(self): pass
    ModelEventLogger(conn=Bad()).record(task_name='sc', event_type='model_disabled')
