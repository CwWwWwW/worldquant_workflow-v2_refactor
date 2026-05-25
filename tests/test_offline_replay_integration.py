import json
from types import SimpleNamespace

from wq_workflow.offline.repository import DecisionSnapshotRepository
from wq_workflow.offline.schema import DecisionAction, DecisionOutcome, DecisionSnapshot
from wq_workflow.offline.service import OfflineReplayService


def test_offline_replay_full_integration_report_and_comparison(tmp_path):
    db_path = tmp_path / "workflow.db"
    report_path = tmp_path / "offline_replay_report.json"
    repo = DecisionSnapshotRepository(db_path=db_path)
    actual = DecisionAction(action_id="a1")
    model = DecisionAction(action_id="a2")
    repo.save_snapshot(DecisionSnapshot(decision_id="d1", decision_type="experiment_arm_selection", alpha_id="alpha1", chosen_action=actual, legacy_choice=actual, model_choice=model))
    repo.save_outcome(DecisionOutcome(outcome_id="o1", decision_id="d1", alpha_id="alpha1", reward=1.0, success=True))
    service = OfflineReplayService(
        config=SimpleNamespace(
            enable_offline_replay=False,
            offline_replay_auto_run=False,
            offline_replay_mode="advisory",
            offline_replay_status_path=str(report_path),
            offline_replay_default_limit=1000,
            offline_replay_min_observable_samples=1,
            offline_replay_baseline_policy="legacy",
            offline_replay_fail_open=True,
            storage_db_path=str(db_path),
        )
    )
    service.startup_check()
    run = service.run_replay()
    assert run.status == "completed"
    data = json.loads(report_path.read_text(encoding="utf-8"))
    assert data["runs"]
    assert data["comparisons"]
    model_decision = next(item for item in service.repository.list_policy_decisions(run.replay_run_id) if item.policy_name == "model_choice")
    assert "insufficient_counterfactual_evidence" in model_decision.reason_codes
    assert model_decision.reward is None
