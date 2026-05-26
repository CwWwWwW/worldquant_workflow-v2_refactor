from __future__ import annotations

from wq_workflow.config import load_config
from wq_workflow.models import WorkflowConfig


def test_explainability_config_defaults():
    cfg = load_config()
    assert cfg.enable_run_explainability is False
    assert cfg.observability_explainability_auto_run is False
    assert cfg.observability_explainability_mode == "explain_only"
    assert cfg.observability_explanation_auto_action is False
    assert cfg.run_explain_report_status_path == "runtime/status/run_explain_report.json"
    assert cfg.daily_observability_report_status_path == "runtime/status/daily_observability_report.json"
    assert cfg.stage7_summary_report_status_path == "runtime/status/stage7_summary_report.json"
    assert cfg.observability_explainability_fail_open is True
    assert WorkflowConfig().enable_run_explainability is False
