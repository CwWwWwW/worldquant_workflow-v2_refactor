from __future__ import annotations

import json
import sqlite3
from types import SimpleNamespace

from wq_workflow.experiment.repository import ExperimentRepository
from wq_workflow.experiment.service import ExperimentService


def test_experiment_integration_tracks_candidate_result_without_reward_change(tmp_path):
    conn = sqlite3.connect(tmp_path / "workflow.db")
    conn.row_factory = sqlite3.Row
    cfg = SimpleNamespace(enable_experiment_tracking=True, default_experiment_id="default_experiment_v1", experiment_status_path=str(tmp_path / "experiment_report.json"), experiment_assignment_mode="tracking_only", enable_refactored_pipeline=False)
    reward = 3.14
    service = ExperimentService(config=cfg, repository=ExperimentRepository(conn=conn))
    assert service.startup_check()["ok"] is True
    assignment = service.assign_candidate({"alpha_id": "Auto_Alpha_001:1", "expression": "rank(close)", "template_family": "seed"})
    result = service.record_result("Auto_Alpha_001:1", {"success": True, "reward": reward, "metrics": {"sharpe": 1.2}, "quality_passed": True})
    service.update_report()

    assert assignment.experiment_id == "default_experiment_v1"
    assert result.reward == reward
    assert reward == 3.14
    assert cfg.enable_refactored_pipeline is False
    payload = json.loads((tmp_path / "experiment_report.json").read_text(encoding="utf-8"))
    assert payload["summaries"]
