from __future__ import annotations

from wq_workflow.dashboard.cli_formatter import CLIStatusFormatter
from wq_workflow.dashboard.dashboard_schema import DashboardRuntimeStatus, DashboardSnapshot


def test_cli_compact_displays_runtime_events_and_evidence_without_long_traceback():
    snapshot = DashboardSnapshot(
        generated_at="now",
        runtime=DashboardRuntimeStatus(
            current_state="WAIT_RESULT",
            current_template="tpl",
            current_alpha_id="a",
            current_iteration=1,
            platform_waiting=True,
            platform_progress=0.5,
            parse_status="idle",
            sc_check_status="running",
            last_reward=0.7,
            last_sc_value=0.2,
            recent_events=[{"time": "t", "level": "ERROR", "state": "WAIT_RESULT", "message": "Traceback " + "x" * 1000}],
            legacy_evidence_summary={"reward_update": {"count": 1}},
        ),
    )
    text = CLIStatusFormatter().format_snapshot(snapshot, compact=True, limit=1)
    assert "state=WAIT_RESULT" in text and "progress=0.5" in text and "Legacy evidence" in text
    assert "x" * 500 not in text
