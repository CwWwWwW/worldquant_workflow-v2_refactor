import unittest

from wq_workflow.orchestrator import is_automation_error
from wq_workflow.simulate import is_automation_result_error, is_nonrecoverable_business_error


class ErrorRoutingTests(unittest.TestCase):
    def test_platform_business_error_is_not_automation(self) -> None:
        text = "Invalid number of inputs for ts_rank"

        self.assertFalse(is_automation_result_error(text))
        self.assertFalse(is_automation_error(text))

    def test_final_correlation_error_is_not_automation(self) -> None:
        text = "[FINAL_CORRELATION] expression too similar to prior alpha"

        self.assertTrue(is_nonrecoverable_business_error(text))
        self.assertFalse(is_automation_result_error(text))
        self.assertFalse(is_automation_error(text))

    def test_run_validator_error_is_automation(self) -> None:
        text = "[AUTOMATION] CLICK_RUN: RUN_NOT_TRIGGERED"

        self.assertTrue(is_automation_result_error(text))
        self.assertTrue(is_automation_error(text))


if __name__ == "__main__":
    unittest.main()
