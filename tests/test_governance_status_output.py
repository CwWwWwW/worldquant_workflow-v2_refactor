from wq_workflow.governance.status_writer import StatusWriter
from wq_workflow.governance.schema import TaskGovernanceState
import json


def test_status_write_multi_task_and_corrupt(tmp_path):
    p=tmp_path/'status.json'
    w=StatusWriter(status_path=p, ml_status_path=None, root=tmp_path)
    assert w.write_task(TaskGovernanceState(task_name='sc'))
    assert w.write_task(TaskGovernanceState(task_name='policy'))
    data=json.loads(p.read_text())
    assert {'sc','policy'} <= set(data['tasks'])
    p.write_text('{bad')
    assert w.write_task(TaskGovernanceState(task_name='parent'))
    assert any(x.name.startswith('status.json.broken') for x in tmp_path.iterdir())
