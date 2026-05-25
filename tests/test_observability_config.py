from __future__ import annotations

from wq_workflow.config import load_config


def test_observability_config_defaults():
    cfg = load_config()
    assert cfg.enable_observability_metrics is True
    assert cfg.observability_auto_collect is False
    assert cfg.observability_mode == "metrics_only"
    assert cfg.enable_observability_alerts is False
    assert cfg.enable_observability_drift_detection is False
    assert cfg.enable_observability_diagnosis is False
    assert cfg.enable_run_explainability is False
    assert cfg.observability_auto_remediation is False
