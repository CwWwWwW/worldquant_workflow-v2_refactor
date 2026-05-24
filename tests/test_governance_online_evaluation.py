import json, sqlite3
from types import SimpleNamespace
from wq_workflow.data.migrations import initialize_refactor_tables
from wq_workflow.governance.online_evaluation import OnlineEvaluator


def test_sc_mae_rules_and_persist(tmp_path):
    conn = sqlite3.connect(tmp_path/'db.sqlite')
    initialize_refactor_tables(conn)
    cfg = SimpleNamespace(sc_online_eval_min_samples=2, sc_model_max_mae=0.1)
    for i,(learned, actual) in enumerate([(0.1,0.1),(0.2,0.6)]):
        conn.execute('insert into ml_prediction_audit(prediction_id,task_name,model_version,prediction_json,raw_payload,created_at) values(?,?,?,?,?,?)', (str(i),'sc','v1',json.dumps({'learned_local_sc':learned}),json.dumps({'platform_sc_abs_max':actual}),'now'))
    conn.commit()
    r = OnlineEvaluator(conn=conn, config=cfg).evaluate_task('sc','v1')
    assert r.sample_count == 2
    assert r.recommended_action == 'disable_model'
    assert conn.execute('select count(*) from ml_online_evaluation').fetchone()[0] == 1


def test_sc_insufficient_samples_keep_shadow(tmp_path):
    conn = sqlite3.connect(tmp_path/'db.sqlite'); initialize_refactor_tables(conn)
    cfg = SimpleNamespace(sc_online_eval_min_samples=30, sc_model_max_mae=0.1)
    r = OnlineEvaluator(conn=conn, config=cfg).evaluate_task('sc','v1')
    assert r.recommended_action == 'keep_shadow'
