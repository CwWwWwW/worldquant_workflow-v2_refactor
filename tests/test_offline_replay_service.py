from types import SimpleNamespace

from wq_workflow.offline.repository import DecisionSnapshotRepository
from wq_workflow.offline.schema import DecisionAction, DecisionOutcome, DecisionSnapshot
from wq_workflow.offline.service import OfflineReplayService


def _cfg(db_path, report_path, **overrides):
    data = {
        "enable_offline_replay": False,
        "offline_replay_auto_run": False,
        "offline_replay_mode": "advisory",
        "offline_replay_status_path": str(report_path),
        "offline_replay_default_limit": 1000,
        "offline_replay_min_observable_samples": 30,
        "offline_replay_baseline_policy": "legacy",
        "offline_replay_fail_open": True,
        "storage_db_path": str(db_path),
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def test_offline_replay_service_disabled_startup_does_not_run(tmp_path):
    db_path = tmp_path / "workflow.db"
    service = OfflineReplayService(config=_cfg(db_path, tmp_path / "report.json"))
    result = service.startup_check()
    assert result["ok"]
    assert result["enabled"] is False
    assert service.list_replay_runs() == []


def test_offline_replay_service_manual_run_and_latest_report(tmp_path):
    db_path = tmp_path / "workflow.db"
    repo = DecisionSnapshotRepository(db_path=db_path)
    action = DecisionAction(action_id="a1")
    repo.save_snapshot(DecisionSnapshot(decision_id="d1", chosen_action=action, legacy_choice=action))
    repo.save_outcome(DecisionOutcome(outcome_id="o1", decision_id="d1", reward=1.0, success=True))
    service = OfflineReplayService(config=_cfg(db_path, tmp_path / "report.json"))
    service.startup_check()
    run = service.run_replay()
    assert run.status == "completed"
    assert service.get_latest_report()["latest_replay_run_id"] == run.replay_run_id
