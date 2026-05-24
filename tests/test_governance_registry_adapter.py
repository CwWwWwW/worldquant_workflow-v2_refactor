import sqlite3, json
from pathlib import Path
from wq_workflow.data.migrations import initialize_refactor_tables
from wq_workflow.governance.registry_adapter import RegistryAdapter
from wq_workflow.learning.ml.model_registry import ModelRegistry


def seed(conn, root, task='sc', version='v1', active=1):
    d = root/task/version; d.mkdir(parents=True)
    (d/'model.joblib').write_text('x')
    (d/'feature_schema.json').write_text('{}')
    conn.execute('insert or replace into ml_model_registry(model_id,task_name,model_version,model_path,is_active,created_at,raw_payload) values(?,?,?,?,?,?,?)', (f'{task}:{version}',task,version,str(d/'model.joblib'),active,'now',json.dumps({})))
    conn.commit()


def test_disable_and_weight(tmp_path):
    conn=sqlite3.connect(tmp_path/'db.sqlite'); initialize_refactor_tables(conn); seed(conn,tmp_path/'models')
    reg=ModelRegistry(db_conn=conn, model_root=tmp_path/'models')
    a=RegistryAdapter(reg)
    assert a.update_model_weight('sc','v1',2.0)
    assert a.disable_active_model('sc','bad')
    assert conn.execute('select is_active from ml_model_registry where task_name="sc"').fetchone()[0] == 0


def test_rollback_previous(tmp_path):
    conn=sqlite3.connect(tmp_path/'db.sqlite'); initialize_refactor_tables(conn); seed(conn,tmp_path/'models','sc','v1',0); seed(conn,tmp_path/'models','sc','v2',1)
    reg=ModelRegistry(db_conn=conn, model_root=tmp_path/'models')
    a=RegistryAdapter(reg)
    assert a.rollback_to_previous_active('sc')
