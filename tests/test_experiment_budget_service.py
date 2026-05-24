from __future__ import annotations

from types import SimpleNamespace

from wq_workflow.experiment.repository import ExperimentRepository
from wq_workflow.experiment.schema import ExperimentSummary
from wq_workflow.experiment.service import ExperimentService


def _cfg(path):
    return SimpleNamespace(
        enable_experiment_tracking=True,
        enable_experiment_budgeting=True,
        enable_experiment_design=True,
        default_experiment_id="exp",
        experiment_status_path=str(path),
        experiment_assignment_mode="tracking_only",
        experiment_budget_total_hint=200,
    )


def test_budget_service_generate_get_recommend_and_report(tmp_path):
    repo = ExperimentRepository(db_path=tmp_path / "workflow.db")
    service = ExperimentService(config=_cfg(tmp_path / "report.json"), repository=repo)
    assert service.startup_check()["ok"]
    repo.update_summary("exp", "legacy_baseline")
    # Insert summary directly to avoid changing result semantics in this test.
    with repo.connection() as conn:
        conn.execute("INSERT OR REPLACE INTO experiment_summaries(summary_id, experiment_id, arm_id, sample_count, success_count, failure_count, avg_reward, avg_platform_sc_abs_max, quality_pass_rate, updated_at, raw_payload) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", ("exp:legacy_baseline", "exp", "legacy_baseline", 50, 30, 20, 0.1, 0.2, 0.4, "2026-01-01T00:00:00+00:00", "{}"))
        conn.commit()
    plan = service.generate_budget_plan()
    assert plan is not None
    assert service.get_current_budget_plan("exp") is not None
    rec = service.recommend_arm({"experiment_id": "exp"})
    assert rec is not None
    result = service.update_report()
    assert result["ok"]


def test_budget_service_disabled_tracking_still_available(tmp_path):
    cfg = _cfg(tmp_path / "report.json")
    cfg.enable_experiment_budgeting = False
    service = ExperimentService(config=cfg, repository=ExperimentRepository(db_path=tmp_path / "workflow.db"))
    assert service.startup_check()["ok"]
    assert service.assign_candidate({"alpha_id": "a1", "is_legacy_baseline": True}) is not None
