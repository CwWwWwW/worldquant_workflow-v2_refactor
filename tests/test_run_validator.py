import unittest

from wq_workflow.models import RunValidation
from wq_workflow.run_validator import RUN_NOT_TRIGGERED, STALE_RESULT, is_plausible_simulation_id


class FakePage:
    def __init__(self, timestamps):
        self.timestamps = list(timestamps)

    async def evaluate(self, script):
        return self.timestamps.pop(0) if self.timestamps else None

    async def wait_for_timeout(self, timeout):
        return None


class RunValidatorTests(unittest.IsolatedAsyncioTestCase):
    async def test_result_without_timestamp_is_stale(self) -> None:
        from wq_workflow.run_validator import validate_result_freshness

        validation = RunValidation(ok=True, click_timestamp=100)
        result = await validate_result_freshness(FakePage([None]), validation)

        self.assertFalse(result.ok)
        self.assertEqual(result.reason, STALE_RESULT)

    async def test_result_older_than_click_is_stale(self) -> None:
        from wq_workflow.run_validator import validate_result_freshness

        validation = RunValidation(ok=True, click_timestamp=100)
        result = await validate_result_freshness(FakePage([99]), validation)

        self.assertFalse(result.ok)
        self.assertEqual(result.reason, STALE_RESULT)

    async def test_old_timestamp_with_stable_consistency_signals_is_fresh(self) -> None:
        from wq_workflow.run_validator import validate_result_freshness

        validation = RunValidation(
            ok=True,
            click_timestamp=100,
            progress_complete=True,
            metrics_detected=True,
            fingerprint_stable=True,
            consistency_signals_present=True,
        )
        result = await validate_result_freshness(FakePage([99]), validation)

        self.assertTrue(result.ok)
        self.assertEqual(result.freshness_score, 90)

    async def test_low_consistency_score_is_stale(self) -> None:
        from wq_workflow.run_validator import validate_result_freshness

        validation = RunValidation(
            ok=True,
            click_timestamp=100,
            progress_complete=True,
            metrics_detected=False,
            fingerprint_stable=False,
            consistency_signals_present=True,
        )
        result = await validate_result_freshness(FakePage([99]), validation)

        self.assertFalse(result.ok)
        self.assertEqual(result.reason, STALE_RESULT)
        self.assertEqual(result.freshness_score, 40)

    async def test_result_newer_than_click_is_fresh(self) -> None:
        from wq_workflow.run_validator import validate_result_freshness

        validation = RunValidation(ok=True, click_timestamp=100)
        result = await validate_result_freshness(FakePage([101]), validation)

        self.assertTrue(result.ok)
        self.assertEqual(result.result_timestamp, 101)

    def test_run_not_triggered_constant(self) -> None:
        self.assertEqual(RUN_NOT_TRIGGERED, "RUN_NOT_TRIGGERED")

    def test_static_resource_token_is_not_plausible_simulation_id(self) -> None:
        self.assertFalse(is_plausible_simulation_id("scrsrc", "resource:path"))
        self.assertFalse(is_plausible_simulation_id("static", "resource:path"))
        self.assertFalse(is_plausible_simulation_id("bundle", "resource:path"))

    def test_realistic_alpha_id_is_plausible(self) -> None:
        self.assertTrue(is_plausible_simulation_id("abc123DEF_456", "data-alpha-id"))

    async def test_read_simulation_id_skips_static_candidate(self) -> None:
        from wq_workflow.run_validator import read_simulation_id

        page = FakePage(
            [
                [
                    {"value": "scrsrc", "source": "resource:path"},
                    {"value": "abc123DEF_456", "source": "data-alpha-id"},
                ]
            ]
        )

        self.assertEqual(await read_simulation_id(page), "abc123DEF_456")

    async def test_validate_run_triggered_ignores_static_candidate(self) -> None:
        from wq_workflow.run_validator import validate_run_triggered

        page = FakePage([[{"value": "scrsrc", "source": "resource:path"}]])
        result = await validate_run_triggered(
            page,
            old_simulation_id="",
            click_timestamp=100,
            timeout=0.01,
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.new_simulation_id, "")


if __name__ == "__main__":
    unittest.main()
