from __future__ import annotations

from types import SimpleNamespace

from wq_workflow.observability.explainability_service import ExplainabilityService


def _cfg(tmp_path, **overrides):
    data = dict(storage_db_path=str(tmp_path / "workflow.db"), enable_run_explainability=False, observability_explainability_auto_run=False, observability_explainability_fail_open=True, run_explain_report_status_path="runtime/status/run_explain_report.json", daily_observability_report_status_path="runtime/status/daily_observability_report.json", stage7_summary_report_status_path="runtime/status/stage7_summary_report.json", observability_explanation_recent_limit=1000)
    data.update(overrides)
    return SimpleNamespace(**data)


def test_explainability_service_startup_manual_generate(tmp_path):
    svc = ExplainabilityService(config=_cfg(tmp_path), root=tmp_path)
    startup = svc.startup_check()
    assert startup["enabled"] is False and "explanations" not in startup
    result = svc.generate_explanations()
    assert result["ok"] is True and result["mode"] == "explain_only"
    assert (tmp_path / "runtime/status/run_explain_report.json").exists()
    assert svc.get_latest_run_explanation() is not None
    assert svc.get_latest_daily_report() is not None
    assert svc.get_latest_stage_summary() is not None
    assert svc.get_status()["auto_action_allowed"] is False
