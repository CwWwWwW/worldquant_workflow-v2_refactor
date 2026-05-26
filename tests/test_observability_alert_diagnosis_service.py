from __future__ import annotations

from types import SimpleNamespace

from wq_workflow.observability.alert_diagnosis_service import AlertDiagnosisService
from wq_workflow.observability.repository import ObservabilityRepository
from wq_workflow.observability.schema import ObservabilityMetric, ObservabilitySnapshot, ObservabilitySourceStatus


def _cfg(tmp_path, **overrides):
    data = dict(storage_db_path=str(tmp_path / "workflow.db"), observability_alerts_status_path=str(tmp_path / "runtime/status/observability_alerts.json"), observability_diagnosis_status_path=str(tmp_path / "runtime/status/health_diagnosis.json"), enable_observability_alerts=False, enable_observability_drift_detection=False, enable_observability_diagnosis=False, observability_diagnostics_auto_run=False, observability_diagnosis_fail_open=True)
    data.update(overrides)
    return SimpleNamespace(**data)


def test_observability_alert_diagnosis_service_manual_run_no_auto(tmp_path):
    cfg = _cfg(tmp_path)
    obs_repo = ObservabilityRepository(db_path=cfg.storage_db_path)
    obs_repo.initialize()
    metrics = [ObservabilityMetric(source="workflow", metric_name="workflow.recent_failure_count", value=v, timestamp=str(i)) for i, v in enumerate([1, 1, 10])]
    obs_repo.save_snapshot(ObservabilitySnapshot(snapshot_id="s1", metrics=metrics, source_statuses=[ObservabilitySourceStatus(source="workflow", available=True)]))
    svc = AlertDiagnosisService(config=cfg, root=tmp_path, observability_repository=obs_repo)
    startup = svc.startup_check()
    assert startup["enabled"] is False and "diagnostics" not in startup
    result = svc.run_diagnostics()
    assert result["ok"] is True
    assert (tmp_path / "runtime/status/observability_alerts.json").exists()
    assert (tmp_path / "runtime/status/health_diagnosis.json").exists()
    assert svc.get_latest_diagnosis() is not None
