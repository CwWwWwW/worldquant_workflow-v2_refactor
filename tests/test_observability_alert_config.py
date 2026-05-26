from __future__ import annotations

from wq_workflow.config import load_config


def test_observability_alert_config_defaults():
    cfg = load_config()
    assert cfg.enable_observability_alerts is False
    assert cfg.enable_observability_drift_detection is False
    assert cfg.enable_observability_diagnosis is False
    assert cfg.observability_diagnostics_auto_run is False
    assert cfg.observability_alert_auto_emit is False
    assert cfg.observability_auto_remediation is False
    assert cfg.observability_alert_mode == "advisory"
