import json

from wq_workflow.config import load_config
from wq_workflow.models import WorkflowConfig


def test_decision_snapshot_config_defaults():
    cfg = WorkflowConfig()
    assert cfg.enable_decision_snapshots is True
    assert cfg.enable_offline_replay is False
    assert cfg.enable_counterfactual_evaluation is False
    assert cfg.decision_snapshot_fail_open is True
    assert cfg.decision_snapshot_status_path == "runtime/status/decision_snapshot_status.json"


def test_config_example_defaults():
    data = json.loads(open("config.example.json", encoding="utf-8").read())
    assert data["enable_decision_snapshots"] is True
    assert data["enable_offline_replay"] is False
    assert data["enable_counterfactual_evaluation"] is False
