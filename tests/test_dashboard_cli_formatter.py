from __future__ import annotations

from wq_workflow.dashboard.cli_formatter import CLIStatusFormatter
from wq_workflow.dashboard.dashboard_schema import DashboardRuntimeStatus, DashboardSnapshot


def test_cli_formatter_compact_truncates_and_summarizes():
    snapshot = DashboardSnapshot(
        generated_at="now",
        runtime=DashboardRuntimeStatus(
            current_state="WAIT_RESULT",
            recent_events=[{"time": "t", "level": "ERROR", "state": "WAIT_RESULT", "message": "x" * 1000}],
        ),
        raw_payload={"log_errors": [{"time": "t", "level": "ERROR", "message": "Traceback " + "y" * 1000}]},
    )
    text = CLIStatusFormatter().format_snapshot(snapshot, compact=True, limit=1)
    assert "Runtime:" in text and "ML:" in text and "Strategy:" in text and "Observability:" in text
    assert len(text.splitlines()) < 25
    assert "x" * 500 not in text
    assert "y" * 500 not in text


def test_cli_formatter_json_summary_limit():
    summary = CLIStatusFormatter().summarize_json({str(i): list(range(10)) for i in range(20)}, max_keys=3)
    assert len(summary) == 3
    assert summary["0"]["count"] == 10
