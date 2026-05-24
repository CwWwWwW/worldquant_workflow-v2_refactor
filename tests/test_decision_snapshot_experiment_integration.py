from types import SimpleNamespace

from wq_workflow.experiment.repository import ExperimentRepository
from wq_workflow.experiment.service import ExperimentService
from wq_workflow.offline.repository import DecisionSnapshotRepository
from wq_workflow.offline.service import DecisionSnapshotService


def test_experiment_assignment_and_budget_record_snapshots(tmp_path):
    cfg = SimpleNamespace(
        enable_experiment_tracking=True,
        enable_decision_snapshots=True,
        default_experiment_id="default_experiment_v1",
        experiment_status_path=str(tmp_path / "experiment_report.json"),
        experiment_assignment_mode="tracking_only",
        experiment_budget_mode="advisory",
        experiment_budget_total_hint=10,
        experiment_budget_legacy_min_ratio=0.15,
        experiment_budget_random_min_ratio=0.05,
        experiment_budget_treatment_max_ratio=0.4,
        experiment_budget_min_samples_for_adjustment=30,
        experiment_budget_high_failure_rate_threshold=0.7,
        experiment_budget_high_sc_abs_max_threshold=0.7,
        experiment_budget_high_quality_pass_threshold=0.3,
        experiment_budget_allow_governance_veto=True,
        experiment_budget_fail_open_tracking_only=True,
    )
    snap_service = DecisionSnapshotService(config=cfg, repository=DecisionSnapshotRepository(db_path=tmp_path / "workflow.db"))
    snap_service.startup_check()
    service = ExperimentService(config=cfg, repository=ExperimentRepository(db_path=tmp_path / "workflow.db"), decision_snapshot_service=snap_service)
    assert service.startup_check()["ok"] is True
    budget = service.generate_budget_plan(total_budget_hint=10)
    assignment = service.assign_candidate({"alpha_id": "a1", "mutation_type": "m"})
    assert budget is not None and assignment is not None
    snapshots = snap_service.repository.list_snapshots(limit=20)
    types = {item.decision_type for item in snapshots}
    assert "budget_plan_selection" in types
    assert "experiment_arm_selection" in types
    assert any(item.experiment_id == "default_experiment_v1" for item in snapshots)
