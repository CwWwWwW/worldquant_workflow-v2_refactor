from __future__ import annotations

import json

from wq_workflow.observability.explanation_reporter import ExplanationReporter
from wq_workflow.observability.explanation_schema import DailyRunReport, RunExplanation, StageSummaryReport


def test_explanation_reporter_writes_and_backs_up_broken_json(tmp_path):
    reporter = ExplanationReporter(root=tmp_path)
    run_path = tmp_path / "runtime/status/run_explain_report.json"
    run_path.parent.mkdir(parents=True)
    run_path.write_text("{broken", encoding="utf-8")
    result = reporter.write_all(RunExplanation(run_summary="ok", auto_action_allowed=True), DailyRunReport(date="2026-05-26"), StageSummaryReport())
    assert result["run"]["ok"] and result["daily"]["ok"] and result["stage"]["ok"]
    payload = json.loads(run_path.read_text(encoding="utf-8"))
    assert payload["mode"] == "explain_only"
    assert payload["auto_action_allowed"] is False
    assert list(run_path.parent.glob("run_explain_report.json.broken.*.bak"))
    assert (tmp_path / "runtime/status/daily_observability_report.json").exists()
    assert (tmp_path / "runtime/status/stage7_summary_report.json").exists()
