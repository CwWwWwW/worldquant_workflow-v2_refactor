from __future__ import annotations

from wq_workflow.config import load_config
from wq_workflow.models import WorkflowConfig


def test_experiment_config_defaults():
    cfg = WorkflowConfig()
    assert cfg.enable_experiment_tracking is True
    assert cfg.enable_experiment_design is False
    assert cfg.enable_experiment_budgeting is False
    assert cfg.experiment_assignment_mode == "tracking_only"


def test_load_config_experiment_defaults():
    cfg = load_config()
    assert getattr(cfg, "enable_experiment_tracking", None) is True
    assert getattr(cfg, "enable_experiment_design", None) is False
    assert getattr(cfg, "enable_experiment_budgeting", None) is False
    assert getattr(cfg, "experiment_assignment_mode", None) == "tracking_only"
