from __future__ import annotations

from types import SimpleNamespace

from wq_workflow.observability.service import ObservabilityService


def _cfg(tmp_path, **overrides):
    data = dict(storage_db_path=str(tmp_path / "workflow.db"), observability_metrics_status_path=str(tmp_path / "runtime/status/observability_metrics.json"), enable_observability_metrics=True, observability_auto_collect=False, observability_mode="metrics_only", observability_fail_open=True)
    data.update(overrides)
    return SimpleNamespace(**data)


def test_observability_service_startup_manual_collect_and_disabled_no_auto(tmp_path):
    cfg = _cfg(tmp_path, enable_observability_metrics=False)
    service = ObservabilityService(config=cfg, root=tmp_path)
    startup = service.startup_check()
    assert startup["enabled"] is False and "collect" not in startup
    result = service.collect_metrics()
    assert result["ok"] is True
    assert service.get_latest_snapshot() is not None
    assert service.get_latest_summary() is not None
    status = service.get_status()
    assert status["mode"] == "metrics_only" and status["alerts_enabled"] is False and status["drift_detection_enabled"] is False
