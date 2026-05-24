from __future__ import annotations

import sqlite3

from wq_workflow.experiment.assignment import make_assignment
from wq_workflow.experiment.planner import DefaultExperimentPlanner
from wq_workflow.experiment.repository import ExperimentRepository
from wq_workflow.experiment.schema import ExperimentResult


def test_repository_plan_assignment_result_summary_idempotent(tmp_path):
    conn = sqlite3.connect(tmp_path / "workflow.db")
    conn.row_factory = sqlite3.Row
    repo = ExperimentRepository(conn=conn)
    assert repo.initialize()["ok"] is True

    plan = DefaultExperimentPlanner().build_default_plan()
    assert repo.save_plan(plan)["ok"] is True
    assert repo.get_plan(plan.experiment_id).experiment_id == plan.experiment_id
    assert repo.get_active_plans()[0].experiment_id == plan.experiment_id

    assignment = make_assignment(plan.experiment_id, "default_treatment", {"alpha_id": "a1", "expression": "rank(close)", "raw": object()})
    assert repo.save_assignment(assignment)["ok"] is True
    assert repo.save_assignment(assignment)["ok"] is True
    assert repo.get_assignment(assignment.assignment_id).alpha_id == "a1"
    assert repo.find_assignment_by_alpha("a1").assignment_id == assignment.assignment_id

    result = ExperimentResult("r1", assignment.assignment_id, plan.experiment_id, assignment.arm_id, alpha_id="a1", success=True, reward=2.0, sharpe=1.0, fitness=0.5, platform_sc_abs_max=0.1, quality_passed=True, raw_payload={"bad": object()})
    assert repo.save_result(result)["ok"] is True
    assert repo.save_result(result)["ok"] is True
    assert len(repo.list_results(plan.experiment_id)) == 1

    summary = repo.update_summary(plan.experiment_id, assignment.arm_id)
    assert summary.sample_count == 1
    assert summary.success_count == 1
    assert summary.avg_reward == 2.0
    assert repo.list_summaries(plan.experiment_id)[0].quality_pass_rate == 1.0
