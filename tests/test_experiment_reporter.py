from __future__ import annotations

import json
import sqlite3

from wq_workflow.experiment.assignment import make_assignment
from wq_workflow.experiment.planner import DefaultExperimentPlanner
from wq_workflow.experiment.repository import ExperimentRepository
from wq_workflow.experiment.reporter import ExperimentReporter
from wq_workflow.experiment.schema import ExperimentResult


def test_reporter_writes_multi_arm_and_recovers_corrupt_json(tmp_path):
    conn = sqlite3.connect(tmp_path / "workflow.db")
    conn.row_factory = sqlite3.Row
    repo = ExperimentRepository(conn=conn)
    repo.initialize()
    plan = DefaultExperimentPlanner().build_default_plan()
    repo.save_plan(plan)
    for arm_id, alpha_id, reward in [("default_treatment", "a1", 1.0), ("legacy_baseline", "a2", -1.0)]:
        assignment = make_assignment(plan.experiment_id, arm_id, {"alpha_id": alpha_id})
        repo.save_assignment(assignment)
        repo.save_result(ExperimentResult(f"r-{alpha_id}", assignment.assignment_id, plan.experiment_id, arm_id, alpha_id=alpha_id, success=reward > 0, reward=reward))
        repo.update_summary(plan.experiment_id, arm_id)

    path = tmp_path / "status" / "experiment_report.json"
    path.parent.mkdir(parents=True)
    path.write_text("{broken", encoding="utf-8")
    reporter = ExperimentReporter(repository=repo, status_path=path)
    assert reporter.update()["ok"] is True
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert len(payload["summaries"]) == 2
    assert list(path.parent.glob("experiment_report.json.corrupt.*"))
