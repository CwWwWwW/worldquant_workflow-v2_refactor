import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from wq_workflow.models import RunValidation, WorkflowConfig
from wq_workflow.simulate import collect_and_validate_result_with_stale_downgrade


class FsmParseResultTests(unittest.IsolatedAsyncioTestCase):
    async def test_stale_result_downgrades_before_rebuild_error(self) -> None:
        ctx = SimpleNamespace(
            page=object(),
            config=WorkflowConfig(),
            alpha_name="Auto_Alpha_001",
            old_simulation_id="old123",
            new_simulation_id="new123",
            click_timestamp=100.0,
            simulation_session_id="session-1",
            page_text="",
            result_timestamp=None,
            result_fingerprint="",
            result_stable_count=3,
            freshness_score=None,
            progress_complete=True,
            metrics_stable=True,
        )

        stale = RunValidation(ok=False, result_timestamp=99, freshness_score=40, reason="STALE_RESULT")
        fresh = RunValidation(
            ok=True,
            result_timestamp=99,
            result_fingerprint="fp",
            freshness_score=90,
            result_stable_count=3,
        )

        with (
            patch(
                "wq_workflow.simulate.collect_result_text",
                AsyncMock(return_value="IS Summary Sharpe 1.32 Fitness 1.54 Turnover 20.69% Margin 27.27 5 PASS"),
            ),
            patch("wq_workflow.simulate.ensure_simulate_auth", AsyncMock(return_value=None)),
            patch("wq_workflow.simulate.validate_result_freshness", AsyncMock(side_effect=[stale, stale, fresh])),
            patch("wq_workflow.simulate.soft_refresh_result_metrics", AsyncMock(return_value=None)) as soft_refresh,
            patch("wq_workflow.simulate.requery_result_panel", AsyncMock(return_value=None)) as requery,
            patch("wq_workflow.simulate.log_state_event"),
        ):
            result = await collect_and_validate_result_with_stale_downgrade(ctx)

        self.assertTrue(result.ok)
        self.assertEqual(result.freshness_score, 90)
        soft_refresh.assert_awaited_once()
        requery.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
