import json

from wq_workflow.offline.replay_reporter import ReplayReporter
from wq_workflow.offline.replay_repository import ReplayRepository
from wq_workflow.offline.schema import ReplayComparison, ReplayPolicyMetrics, ReplayRun


def test_replay_reporter_writes_report_and_backs_up_corrupt_json(tmp_path):
    repo = ReplayRepository(db_path=tmp_path / "workflow.db")
    repo.initialize()
    repo.save_replay_run(ReplayRun(replay_run_id="r1", name="run", status="completed", policies=["legacy"], sample_count=1, observable_count=1))
    repo.save_policy_metrics(ReplayPolicyMetrics(replay_run_id="r1", policy_name="legacy", sample_count=1, observable_count=1, coverage_rate=1.0))
    repo.save_comparison(ReplayComparison(comparison_id="c1", replay_run_id="r1", baseline_policy="legacy", challenger_policy="budget_choice"))
    path = tmp_path / "offline_replay_report.json"
    path.write_text("{bad", encoding="utf-8")
    result = ReplayReporter(repository=repo, status_path=path).update(enabled=False, latest_replay_run_id="r1")
    assert result["ok"]
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["runs"]
    assert data["metrics"]
    assert data["comparisons"]
    assert list(tmp_path.glob("offline_replay_report.json.corrupt.*.bak"))
