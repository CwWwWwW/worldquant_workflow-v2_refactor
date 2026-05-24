from __future__ import annotations

import sqlite3

from wq_workflow.experiment.budget import ExperimentBudgetAllocation, ExperimentBudgetPlan, ExperimentBudgetSnapshot
from wq_workflow.experiment.repository import ExperimentRepository
from wq_workflow.experiment.schema import ExperimentSummary


def test_budget_repository_save_get_list_idempotent(tmp_path):
    conn = sqlite3.connect(tmp_path / "workflow.db")
    repo = ExperimentRepository(conn=conn)
    repo.initialize()
    allocation = ExperimentBudgetAllocation("a1", "exp", "legacy_baseline", 1.0)
    plan = ExperimentBudgetPlan("p1", "exp", allocations=[allocation], total_budget_hint=200)
    assert repo.save_budget_plan(plan)["ok"]
    assert repo.save_budget_plan(plan)["ok"]
    latest = repo.get_latest_budget_plan("exp")
    assert latest is not None
    assert latest.budget_plan_id == "p1"
    assert latest.allocations[0].arm_id == "legacy_baseline"
    assert repo.list_budget_plans("exp")[0].budget_plan_id == "p1"
    snapshot = ExperimentBudgetSnapshot("s1", "p1", "exp", allocations_json=[allocation.to_dict()])
    assert repo.save_budget_snapshot(snapshot)["ok"]
    assert repo.list_budget_snapshots("exp")[0].snapshot_id == "s1"

    # Existing 4A summary path remains usable.
    conn.execute("INSERT OR REPLACE INTO experiment_summaries(summary_id, experiment_id, arm_id, sample_count, success_count, failure_count, raw_payload) VALUES (?, ?, ?, ?, ?, ?, ?)", ("exp:a", "exp", "a", 1, 1, 0, "{}"))
    assert isinstance(repo.list_summaries("exp")[0], ExperimentSummary)
