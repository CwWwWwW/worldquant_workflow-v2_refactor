from __future__ import annotations

import sqlite3
from types import SimpleNamespace

from wq_workflow.experiment.repository import ExperimentRepository
from wq_workflow.experiment.service import ExperimentService


def test_service_startup_assign_record_report(tmp_path):
    conn = sqlite3.connect(tmp_path / "workflow.db")
    conn.row_factory = sqlite3.Row
    cfg = SimpleNamespace(
        enable_experiment_tracking=True,
        default_experiment_id="default_experiment_v1",
        experiment_status_path=str(tmp_path / "experiment_report.json"),
        experiment_assignment_mode="tracking_only",
    )
    repo = ExperimentRepository(conn=conn)
    service = ExperimentService(config=cfg, repository=repo)

    status = service.startup_check()
    assert status["ok"] is True
    assert repo.get_plan("default_experiment_v1") is not None

    assignment = service.assign_candidate({"alpha_id": "alpha-1", "expression": "rank(close)"})
    assert assignment is not None
    assert assignment.arm_id == "default_treatment"

    result = service.record_result("alpha-1", {"success": True, "reward": 1.5, "metrics": {"sharpe": 1.1, "fitness": 0.9}, "quality_passed": True})
    assert result is not None
    assert repo.list_results("default_experiment_v1")[0].reward == 1.5
    assert service.update_report()["ok"] is True


def test_service_failure_is_not_fatal():
    service = ExperimentService(config=SimpleNamespace(enable_experiment_tracking=True), repository=ExperimentRepository())
    status = service.startup_check()
    assert status["ok"] is False
    assert service.assign_candidate({"alpha_id": "a"}) is None
    assert service.record_result("a", {"success": False}) is None
