import unittest

from wq_workflow.simulate import (
    looks_like_alpha_details_settings_text,
    looks_like_concrete_backtest_result,
    looks_like_platform_error,
    looks_like_result_shell_text,
    result_fingerprint,
    result_matches_current_alpha,
    result_ready_for_current_run,
    stable_result_fingerprint,
)
from wq_workflow.models import PlatformError, SimulationResult
from wq_workflow.orchestrator import is_result_uncertain_result


class ResultDetectionTests(unittest.TestCase):
    def test_alpha_details_settings_menu_is_not_result_shell(self) -> None:
        text = """
        Customize Alpha Details Menu
        Drag the containers to rearrange the Alpha details menu.
        Chart Summary Correlation Testing Status Performance Comparison Properties
        Reset Apply
        """

        self.assertTrue(looks_like_alpha_details_settings_text(text))
        self.assertFalse(looks_like_result_shell_text(text))
        self.assertFalse(looks_like_concrete_backtest_result(text))

    def test_is_summary_metrics_are_result_shell_and_concrete(self) -> None:
        text = """
        IS Summary Period TRAIN TEST IS OS Needs Improvement
        Aggregate Data Sharpe 1.32 Turnover 20.69% Fitness 1.54
        Returns 28.21% Drawdown 11.86% Margin 27.27
        """

        self.assertFalse(looks_like_alpha_details_settings_text(text))
        self.assertTrue(looks_like_result_shell_text(text))
        self.assertTrue(looks_like_concrete_backtest_result(text))

    def test_status_counts_are_result_shell_and_concrete(self) -> None:
        text = """
        IS Testing Status
        5 PASS
        2 FAIL
        1 PENDING
        """

        self.assertTrue(looks_like_result_shell_text(text))
        self.assertTrue(looks_like_concrete_backtest_result(text))

    def test_normal_settings_properties_result_is_not_settings_menu(self) -> None:
        text = """
        Settings USA/D1/TOP3000
        IS Summary Aggregate Data Sharpe -1.46 Turnover 83.01% Fitness -0.55
        Returns -11.93% Drawdown 58.62% Margin -2.87
        Properties Name Auto_Alpha_001_20260505_194416 Category Tags Color
        Simulate Show test period
        """

        self.assertFalse(looks_like_alpha_details_settings_text(text))
        self.assertTrue(looks_like_result_shell_text(text))
        self.assertTrue(looks_like_concrete_backtest_result(text))

    def test_settings_actions_without_customize_title_is_not_settings_menu(self) -> None:
        text = """
        Settings USA/D1/TOP3000
        editor editor-panels settings-content settings-actions
        Properties Name Auto_Alpha_001 Category Tags Color
        Chart Summary Correlation Testing Status Performance Comparison Properties
        """

        self.assertFalse(looks_like_alpha_details_settings_text(text))

    def test_settings_menu_text_does_not_mask_real_result_text(self) -> None:
        text = """
        Customize Alpha Details Menu
        Drag the containers to rearrange the Alpha details menu.
        Reset Apply
        IS Summary Aggregate Data Sharpe 1.18 Turnover 22.4% Fitness 1.05
        Returns 18.2% Drawdown 9.1% Margin 8.4
        """

        self.assertTrue(looks_like_alpha_details_settings_text(text))
        self.assertTrue(looks_like_result_shell_text(text))
        self.assertTrue(looks_like_concrete_backtest_result(text))

    def test_result_uncertain_timeout_does_not_route_as_platform_failure(self) -> None:
        result = SimulationResult(
            ok=False,
            code="rank(close)",
            alpha_name="Auto_Alpha_001",
            error=PlatformError("[AUTOMATION_TIMEOUT] 平台长时间未返回结果"),
        )

        self.assertTrue(is_result_uncertain_result(result))

    def test_real_platform_error_is_not_result_uncertain(self) -> None:
        result = SimulationResult(
            ok=False,
            code="rank(close)",
            alpha_name="Auto_Alpha_001",
            error=PlatformError('Incompatible unit for input of "add" at index 1'),
        )

        self.assertFalse(is_result_uncertain_result(result))

    def test_final_recovery_requires_current_alpha_match(self) -> None:
        text = "Properties Name Auto_Alpha_001 IS Summary Aggregate Data Sharpe 1.3 Fitness 1.1"

        self.assertTrue(result_matches_current_alpha(text, "Auto_Alpha_001", "rank(close)"))
        self.assertFalse(result_matches_current_alpha(text, "Auto_Alpha_002", "rank(volume)"))

    def test_stable_result_fingerprint_ignores_timestamp_changes(self) -> None:
        first = """
        Last Run: 2026-05-14 10:00:00
        IS Summary Aggregate Data Sharpe 1.32 Turnover 20.69% Fitness 1.54 Margin 27.27
        IS Testing Status 5 PASS 2 FAIL 1 PENDING
        """
        second = first.replace("10:00:00", "10:00:06")

        self.assertEqual(stable_result_fingerprint(first), stable_result_fingerprint(second))

    def test_stable_result_fingerprint_changes_when_metrics_change(self) -> None:
        first = "IS Summary Sharpe 1.32 Fitness 1.54 Turnover 20.69% Margin 27.27 5 PASS"
        second = "IS Summary Sharpe 1.33 Fitness 1.54 Turnover 20.69% Margin 27.27 5 PASS"

        self.assertNotEqual(stable_result_fingerprint(first), stable_result_fingerprint(second))

    def test_stable_result_fingerprint_allows_missing_fields(self) -> None:
        self.assertTrue(stable_result_fingerprint("IS Testing Status 1 PASS"))
        self.assertEqual(stable_result_fingerprint("no metrics yet"), "")

    def test_submit_criteria_tutorial_does_not_create_result_fingerprint(self) -> None:
        text = """
        Tutorial Checks: About Alpha Submit Criteria
        Try creating a submittable Alpha!
        Fitness: 1.0 or higher
        Sharpe: 1.25 or higher
        Turnover: between 1% and 70%
        """

        self.assertEqual(result_fingerprint(text), "")
        self.assertFalse(looks_like_result_shell_text(text))

    def test_real_result_with_tutorial_text_still_has_result_fingerprint(self) -> None:
        text = """
        Tutorial Checks: About Alpha Submit Criteria
        Try creating a submittable Alpha!
        Fitness: 1.0 or higher
        Sharpe: 1.25 or higher
        IS Summary Aggregate Data Sharpe 0.92 Turnover 82.08% Fitness 0.42
        Returns 17.37% Drawdown 19.81% Margin 4.23
        IS Testing Status 5 PASS 2 FAIL 1 PENDING
        """

        fingerprint = result_fingerprint(text)
        self.assertIn("sharpe:0.92", fingerprint)
        self.assertIn("fitness:0.42", fingerprint)
        self.assertNotIn("sharpe:1.25", fingerprint)
        self.assertNotIn("fitness:1", fingerprint)
        self.assertIn("fail:2", fingerprint)

    def test_trade_when_exit_trigger_advice_is_not_platform_error(self) -> None:
        text = "trade_when Operator\nTry using exit triggers (e.g. stop-loss) to close position while using trade_when Operator."

        self.assertFalse(looks_like_platform_error(text))
        self.assertFalse(looks_like_platform_error("trade_when Operator"))

    def test_fingerprintless_baseline_shell_accepts_observed_new_result(self) -> None:
        text = """
        IS Summary Aggregate Data Sharpe 2.78 Turnover 82.26% Fitness 2.13
        Returns 48.13% Drawdown 9.57% Margin 11.70
        """

        ready, reason = result_ready_for_current_run(
            current_text=text,
            baseline_fingerprint="",
            baseline_had_result_shell=True,
            observed_start=True,
            max_progress=35,
            elapsed=120,
        )

        self.assertTrue(ready)
        self.assertIn("fingerprintless baseline shell", reason)


if __name__ == "__main__":
    unittest.main()
