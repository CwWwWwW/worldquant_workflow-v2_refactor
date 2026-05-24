import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from wq_workflow.models import RunValidation, WorkflowConfig
from wq_workflow.run_validator import RUN_NOT_TRIGGERED
from wq_workflow.simulate import fsm_click_run


class FsmClickRunTests(unittest.IsolatedAsyncioTestCase):
    async def test_click_run_accepts_page_activity_when_simulation_id_does_not_change(self) -> None:
        ctx = SimpleNamespace(
            page=object(),
            config=WorkflowConfig(),
            selectors=SimpleNamespace(run=["button:has-text('Run')"]),
            old_simulation_id="same123",
            new_simulation_id="",
            click_timestamp=0.0,
            observed_start=False,
            baseline_progress=None,
        )

        with (
            patch("wq_workflow.simulate.read_progress", AsyncMock(return_value=None)),
            patch("wq_workflow.simulate.ensure_simulate_auth", AsyncMock(return_value=None)),
            patch("wq_workflow.simulate.ensure_alpha_details_settings_not_blocking_run", AsyncMock(return_value=None)),
            patch("wq_workflow.simulate.click_run_button", AsyncMock(return_value=None)),
            patch(
                "wq_workflow.simulate.validate_run_triggered",
                AsyncMock(
                    return_value=RunValidation(
                        ok=False,
                        old_simulation_id="same123",
                        new_simulation_id="same123",
                        click_timestamp=100.0,
                        reason=RUN_NOT_TRIGGERED,
                    )
                ),
            ),
            patch("wq_workflow.simulate.run_start_signal_seen", AsyncMock(return_value=True)),
        ):
            await fsm_click_run(ctx)

        self.assertTrue(ctx.observed_start)
        self.assertEqual(ctx.new_simulation_id, "same123")


if __name__ == "__main__":
    unittest.main()
