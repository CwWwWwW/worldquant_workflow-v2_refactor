from __future__ import annotations

from wq_workflow.observability.alert_diagnosis_service import AlertDiagnosisService
from wq_workflow.observability.repository import ObservabilityRepository
from wq_workflow.observability.schema import ObservabilitySnapshot, ObservabilitySourceStatus


def test_observability_alert_offline_integration(tmp_path):
    cfg = type("Cfg", (), {"storage_db_path": str(tmp_path / "workflow.db"), "observability_alerts_status_path": str(tmp_path / "runtime/status/observability_alerts.json"), "observability_diagnosis_status_path": str(tmp_path / "runtime/status/health_diagnosis.json"), "observability_diagnosis_fail_open": True})()
    repo = ObservabilityRepository(db_path=cfg.storage_db_path); repo.initialize()
    repo.save_snapshot(ObservabilitySnapshot(snapshot_id="s1", source_statuses=[ObservabilitySourceStatus(source="offline_replay", available=True, is_stale=True), ObservabilitySourceStatus(source="counterfactual", available=True)]))
    result = AlertDiagnosisService(config=cfg, root=tmp_path, observability_repository=repo).run_diagnostics()
    assert result["ok"] is True
    assert not (tmp_path / "runtime/status/offline_replay_report.json").exists()
