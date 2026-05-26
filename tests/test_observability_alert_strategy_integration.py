from __future__ import annotations

from wq_workflow.observability.alert_diagnosis_service import AlertDiagnosisService
from wq_workflow.observability.repository import ObservabilityRepository
from wq_workflow.observability.schema import ObservabilityMetric, ObservabilitySnapshot, ObservabilitySourceStatus


def test_observability_alert_strategy_integration(tmp_path):
    cfg = type("Cfg", (), {"storage_db_path": str(tmp_path / "workflow.db"), "observability_alerts_status_path": str(tmp_path / "runtime/status/observability_alerts.json"), "observability_diagnosis_status_path": str(tmp_path / "runtime/status/health_diagnosis.json"), "observability_diagnosis_fail_open": True})()
    repo = ObservabilityRepository(db_path=cfg.storage_db_path); repo.initialize()
    metrics = [ObservabilityMetric(source="strategy_budget", metric_name="strategy.budget_max_ratio", value=0.9), ObservabilityMetric(source="strategy", metric_name="strategy.high_sc_risk_count", value=1)]
    repo.save_snapshot(ObservabilitySnapshot(snapshot_id="s1", metrics=metrics, source_statuses=[ObservabilitySourceStatus(source="strategy_budget", available=True)]))
    result = AlertDiagnosisService(config=cfg, root=tmp_path, observability_repository=repo).run_diagnostics()
    assert result["ok"] is True
    assert not (tmp_path / "runtime/status/strategy_budget_report.json").exists()
