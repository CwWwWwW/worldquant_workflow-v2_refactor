from __future__ import annotations

from types import SimpleNamespace

from wq_workflow.experiment.budget import ExperimentBudgetAllocator
from wq_workflow.experiment.repository import ExperimentRepository
from wq_workflow.experiment.schema import ExperimentSummary
from wq_workflow.experiment.service import ExperimentService


def test_budget_integration_from_summaries_refresh_and_assignment_tag(tmp_path):
    cfg = SimpleNamespace(
        enable_experiment_tracking=True,
        enable_experiment_design=True,
        enable_experiment_budgeting=True,
        default_experiment_id="exp",
        experiment_status_path=str(tmp_path / "report.json"),
        experiment_assignment_mode="advisory_budget",
        experiment_budget_total_hint=100,
    )
    repo = ExperimentRepository(db_path=tmp_path / "workflow.db")
    service = ExperimentService(config=cfg, repository=repo)
    assert service.startup_check()["ok"]
    with repo.connection() as conn:
        conn.execute("INSERT OR REPLACE INTO experiment_summaries(summary_id, experiment_id, arm_id, sample_count, success_count, failure_count, avg_reward, avg_platform_sc_abs_max, quality_pass_rate, updated_at, raw_payload) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", ("exp:legacy_baseline", "exp", "legacy_baseline", 60, 40, 20, 0.1, 0.2, 0.4, "2026-01-01T00:00:00+00:00", "{}"))
        conn.commit()
    plan = service.generate_budget_plan()
    assert plan is not None
    assignment = service.assign_candidate({"alpha_id": "a1", "is_legacy_baseline": True})
    assert assignment is not None
    assert assignment.raw_payload.get("budget_plan_id") == plan.budget_plan_id


def test_budget_failure_and_governance_veto_fail_soft():
    class Gov:
        def allow_experiment_arm(self, experiment_id, arm_id, context):
            return False

    allocator = ExperimentBudgetAllocator()
    plan = allocator.build_budget_plan("exp", [ExperimentSummary("exp", "arm", sample_count=50)], governance_service=Gov())
    assert plan.allocations[0].status == "governance_blocked"
    assert plan.allocations[0].suggested_ratio == 0.0
