import unittest

from wq_workflow.template_success_detector import confirm_success_candidate, detect_template_success


class TemplateSuccessDetectorTests(unittest.TestCase):
    def test_average_zero_fail_after_show_test_period_is_success(self) -> None:
        result = detect_template_success(
            """
            IS Summary
            Period TRAIN TEST IS OS Average
            IS Testing Status
            7 PASS
            0 FAIL
            """,
            show_test_period_revealed=True,
        )

        self.assertTrue(result.template_success)
        self.assertEqual(result.fail_count, 0)
        self.assertEqual(result.reason, "average_with_zero_fail")

    def test_strong_zero_fail_after_show_test_period_is_success(self) -> None:
        result = detect_template_success(
            """
            IS Summary
            Period TRAIN TEST IS OS Strong
            IS Testing Status
            8 PASS
            0 FAIL
            """,
            show_test_period_revealed=True,
        )

        self.assertTrue(result.template_success)
        self.assertTrue(result.strong_present)
        self.assertEqual(result.fail_count, 0)
        self.assertEqual(result.reason, "strong_with_zero_fail")

    def test_nonzero_fail_is_not_success(self) -> None:
        result = detect_template_success("Average\n1 FAIL", show_test_period_revealed=True)

        self.assertFalse(result.template_success)
        self.assertEqual(result.reason, "fail_count_nonzero")

    def test_strong_nonzero_fail_is_not_success(self) -> None:
        result = detect_template_success("Strong\n1 FAIL", show_test_period_revealed=True)

        self.assertFalse(result.template_success)
        self.assertTrue(result.strong_present)
        self.assertEqual(result.reason, "fail_count_nonzero")

    def test_missing_average_or_strong_is_not_success(self) -> None:
        result = detect_template_success("IS Testing Status\n0 FAIL", show_test_period_revealed=True)

        self.assertFalse(result.template_success)
        self.assertEqual(result.reason, "average_or_strong_missing")

    def test_missing_show_test_period_is_not_success(self) -> None:
        result = detect_template_success("Average\n0 FAIL", show_test_period_revealed=False)

        self.assertFalse(result.template_success)
        self.assertEqual(result.reason, "show_test_period_not_revealed")

    def test_missing_explicit_fail_count_is_not_success(self) -> None:
        result = detect_template_success("IS Summary\nAverage\nPASS", show_test_period_revealed=True)

        self.assertFalse(result.template_success)
        self.assertEqual(result.reason, "explicit_fail_count_missing")

    def test_navigation_noise_does_not_create_success(self) -> None:
        result = detect_template_success(
            """
            Tutorial Checks
            Average
            0 FAIL
            Try submitting Alphas
            """,
            show_test_period_revealed=True,
        )

        self.assertFalse(result.template_success)
        self.assertEqual(result.reason, "result_scope_missing")

    def test_nonzero_fail_in_scoped_status_overrides_zero_noise(self) -> None:
        result = detect_template_success(
            """
            Sidebar 0 FAIL Average
            IS Summary
            Period TRAIN TEST IS OS Strong
            IS Testing Status
            8 PASS
            1 FAIL
            """,
            show_test_period_revealed=True,
        )

        self.assertFalse(result.template_success)
        self.assertEqual(result.fail_count, 1)
        self.assertEqual(result.reason, "fail_count_nonzero")

    def test_metrics_payload_without_zero_fail_is_success_candidate(self) -> None:
        result = detect_template_success(
            """
            IS Summary
            Aggregate Data Sharpe 1.45 Turnover 22.0% Fitness 1.12
            Returns 18.2% Drawdown 9.1% Margin 8.4
            """,
            show_test_period_revealed=True,
            thresholds={"sharpe_min": 1.25, "fitness_min": 1.0, "turnover_max": 70.0},
        )

        self.assertFalse(result.template_success)
        self.assertTrue(result.candidate_success)
        self.assertTrue(result.result_uncertain)
        self.assertIn("valid_alpha_payload", result.signals)

    def test_nonzero_fail_blocks_success_candidate(self) -> None:
        result = detect_template_success(
            """
            IS Summary
            Period TRAIN TEST IS OS Strong
            Aggregate Data Sharpe 2.1 Turnover 22.0% Fitness 1.4
            IS Testing Status
            1 FAIL
            """,
            show_test_period_revealed=True,
            thresholds={"sharpe_min": 1.25, "fitness_min": 1.0, "turnover_max": 70.0},
        )

        self.assertFalse(result.template_success)
        self.assertFalse(result.candidate_success)
        self.assertEqual(result.reason, "fail_count_nonzero")

    def test_metrics_above_threshold_are_success_candidate(self) -> None:
        result = detect_template_success(
            """
            IS Summary
            Aggregate Data Sharpe 1.45 Turnover 22.0% Fitness 1.12
            Returns 18.2% Drawdown 9.1% Margin 8.4
            """,
            show_test_period_revealed=True,
            thresholds={"sharpe_min": 1.25, "fitness_min": 1.0, "turnover_max": 70.0},
        )

        self.assertTrue(result.candidate_success)
        self.assertIn("score_threshold", result.signals)

    def test_needs_improvement_blocks_payload_candidate(self) -> None:
        result = detect_template_success(
            """
            IS Summary Period TRAIN TEST IS OS Needs Improvement
            Aggregate Data Sharpe 1.45 Turnover 82.0% Fitness 1.12
            Returns 18.2% Drawdown 9.1% Margin 8.4
            """,
            show_test_period_revealed=True,
        )

        self.assertFalse(result.template_success)
        self.assertFalse(result.candidate_success)

    def test_stable_candidate_can_be_confirmed_without_schema_change(self) -> None:
        result = detect_template_success(
            """
            IS Summary
            Aggregate Data Sharpe 1.45 Turnover 22.0% Fitness 1.12
            Returns 18.2% Drawdown 9.1% Margin 8.4
            """,
            show_test_period_revealed=True,
        )

        confirmed = confirm_success_candidate(result, reason="candidate_stabilized:valid_alpha_payload")

        self.assertTrue(confirmed.template_success)
        self.assertFalse(confirmed.result_uncertain)
        self.assertEqual(confirmed.reason, "candidate_stabilized:valid_alpha_payload")


if __name__ == "__main__":
    unittest.main()
