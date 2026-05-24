import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from wq_workflow.models import WorkflowConfig
from wq_workflow.simulate import final_recovery_result_text, result_fingerprint, wait_for_backtest_finished


class WaitResultStabilityTests(unittest.IsolatedAsyncioTestCase):
    async def test_progress_disappears_with_new_concrete_result_uses_stable_window(self) -> None:
        old_result = "IS Summary Aggregate Data Sharpe 1.25 Turnover 50.0% Fitness 1.00 Margin 2.0"
        new_result = """
        IS Summary Period TRAIN TEST IS OS Needs Improvement
        Aggregate Data Sharpe 0.92 Turnover 82.08% Fitness 0.42
        Returns 17.37% Drawdown 19.81% Margin 4.23
        IS Testing Status 5 PASS 2 FAIL 1 PENDING
        """
        config = WorkflowConfig(
            result_stable_reads=2,
            result_poll_interval_seconds=0.5,
            result_dom_stable_window_seconds=0,
            enable_result_consistency_validation=True,
        )
        progress_text = "35% Simulations usually take a few minutes or more. Click here to cancel the simulation."

        with (
            patch("wq_workflow.simulate.read_progress", AsyncMock(side_effect=[10.0, 15.0, 35.0, None, None])),
            patch("wq_workflow.simulate.collect_focused_result_text", AsyncMock(side_effect=[progress_text, progress_text, progress_text, new_result, new_result, new_result, new_result])),
            patch("wq_workflow.simulate.safe_body_text", AsyncMock(return_value=progress_text)),
            patch("wq_workflow.simulate.ensure_simulate_auth", AsyncMock(return_value=None)),
            patch("wq_workflow.simulate.result_shell_visible", AsyncMock(return_value=False)),
            patch("wq_workflow.simulate.show_test_period_button_visible", AsyncMock(return_value=False)),
            patch("wq_workflow.simulate.detect_and_click_show_test_period", AsyncMock(return_value=True)),
            patch("wq_workflow.simulate.reveal_result_panels", AsyncMock(return_value=None)),
            patch("wq_workflow.simulate.detect_platform_errors", AsyncMock(return_value="")),
            patch("wq_workflow.simulate.simulate_run_loading_indicator", AsyncMock(return_value=False)),
            patch("wq_workflow.simulate.read_result_or_body_text", AsyncMock(return_value=new_result)),
            patch("wq_workflow.simulate.result_feature_summary", AsyncMock(return_value="Sharpe 0.92 Fitness 0.42")),
            patch("wq_workflow.simulate.log_state_event"),
            patch("wq_workflow.simulate.asyncio.sleep", AsyncMock(return_value=None)),
        ):
            text = await wait_for_backtest_finished(
                object(),
                config,
                old_result,
                True,
                baseline_progress=None,
                alpha_id="Auto_Alpha_001",
                simulation_session_id="session-1",
            )

        self.assertIn("Sharpe 0.92", text)
        self.assertNotEqual(result_fingerprint(text), result_fingerprint(old_result))

    async def test_final_recovery_validates_and_returns_concrete_result(self) -> None:
        old_result = "IS Summary Aggregate Data Sharpe 1.25 Turnover 50.0% Fitness 1.00 Margin 2.0"
        new_result = """
        IS Summary Aggregate Data Sharpe 0.92 Turnover 82.08% Fitness 0.42
        Returns 17.37% Drawdown 19.81% Margin 4.23
        IS Testing Status 5 PASS 2 FAIL 1 PENDING
        """

        with (
            patch("wq_workflow.simulate.asyncio.sleep", AsyncMock(return_value=None)),
            patch("wq_workflow.simulate.ensure_simulate_auth", AsyncMock(return_value=None)),
            patch("wq_workflow.simulate.reveal_result_panels", AsyncMock(return_value=None)),
            patch("wq_workflow.simulate.collect_result_text", AsyncMock(return_value=new_result)),
            patch(
                "wq_workflow.simulate.detect_current_success_state",
                AsyncMock(return_value=SimpleNamespace(template_success=False, candidate_success=False)),
            ),
        ):
            text = await final_recovery_result_text(
                object(),
                WorkflowConfig(),
                baseline_fingerprint=result_fingerprint(old_result),
                baseline_had_result_shell=True,
                observed_start=True,
                max_progress=35,
                started=0,
            )

        self.assertIn("Sharpe 0.92", text)


if __name__ == "__main__":
    unittest.main()
