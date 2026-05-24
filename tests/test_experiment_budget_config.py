from __future__ import annotations

from wq_workflow.config import load_config
from wq_workflow.models import WorkflowConfig


def test_experiment_budget_config_defaults():
    cfg = WorkflowConfig()
    assert cfg.enable_experiment_tracking is True
    assert cfg.enable_experiment_design is True
    assert cfg.enable_experiment_budgeting is True
    assert cfg.experiment_budget_mode == "advisory"
    assert cfg.experiment_assignment_mode in {"tracking_only", "advisory_budget"}
    assert cfg.experiment_assignment_mode != "hard_budget"
    assert cfg.experiment_budget_legacy_min_ratio == 0.15
    assert cfg.experiment_budget_random_min_ratio == 0.05
    assert cfg.experiment_budget_treatment_max_ratio == 0.40


def test_load_config_experiment_budget_defaults():
    cfg = load_config()
    assert getattr(cfg, "enable_experiment_tracking", None) is True
    assert getattr(cfg, "enable_experiment_design", None) is True
    assert getattr(cfg, "enable_experiment_budgeting", None) is True
    assert getattr(cfg, "experiment_budget_mode", None) == "advisory"
