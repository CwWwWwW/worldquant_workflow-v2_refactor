import json

from wq_workflow.offline.repository import DecisionSnapshotRepository
from wq_workflow.offline.reporter import DecisionSnapshotReporter
from wq_workflow.offline.schema import DecisionSnapshotSummary


def test_reporter_writes_and_recovers_corrupt_json(tmp_path):
    class Repo:
        def list_summaries(self):
            return [DecisionSnapshotSummary(decision_type="parent_selection", sample_count=1)]
        def count_snapshots(self):
            return 1
        def count_outcomes(self):
            return 0
    path = tmp_path / "decision_snapshot_status.json"
    path.write_text("{bad", encoding="utf-8")
    reporter = DecisionSnapshotReporter(repository=Repo(), status_path=path)
    assert reporter.update()["ok"] is True
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["snapshot_count"] == 1
    assert list(tmp_path.glob("*.bak"))


def test_reporter_write_failure_not_fatal(tmp_path):
    path = tmp_path / "missing" / "status.json"
    reporter = DecisionSnapshotReporter(repository=None, status_path=path)
    assert reporter.update()["ok"] is True
