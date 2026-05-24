from __future__ import annotations

import json

from wq_workflow.experiment.budget import ExperimentBudgetAllocation, ExperimentBudgetPlan
from wq_workflow.experiment.repository import ExperimentRepository
from wq_workflow.experiment.reporter import ExperimentReporter


def test_budget_reporter_includes_budgeting_and_recovers_corrupt_json(tmp_path):
    repo = ExperimentRepository(db_path=tmp_path / "workflow.db")
    repo.initialize()
    plan = ExperimentBudgetPlan("p1", "exp", allocations=[ExperimentBudgetAllocation("a1", "exp", "legacy_baseline", 1.0)])
    repo.save_budget_plan(plan)
    path = tmp_path / "experiment_report.json"
    path.write_text("{bad", encoding="utf-8")
    reporter = ExperimentReporter(repository=repo, status_path=path)
    result = reporter.update()
    assert result["ok"]
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert "summaries" in payload
    assert payload["budgeting"]["latest_budget_plan_id"] == "p1"
    assert list(tmp_path.glob("experiment_report.json.corrupt.*"))
