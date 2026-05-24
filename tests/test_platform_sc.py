import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from wq_workflow.candidate_pool import CandidatePool, _selection_score
from wq_workflow.models import SimulationResult, WorkflowConfig
from wq_workflow.platform_sc import (
    apply_correlation_quality,
    classify_platform_sc_text,
    is_platform_sc_too_high,
    parse_platform_sc_text,
    sc_reward_multiplier,
    strong_feedback_allowed,
)
from wq_workflow.reward_engine import RewardEngine
from wq_workflow.simulate import merge_platform_sc_metrics, run_platform_sc_check_after_backtest


class PlatformSelfCorrelationTests(unittest.TestCase):
    def test_pending_text_is_not_complete(self) -> None:
        parsed = parse_platform_sc_text("Self-correlation check pending. Loading / checking correlation.")
        self.assertEqual(classify_platform_sc_text("Self-correlation check pending. Loading / checking correlation.", parsed), "pending")
        self.assertIsNone(parsed["abs_max"])

    def test_labeled_values_parse_max_min_abs_max(self) -> None:
        parsed = parse_platform_sc_text("Self-correlation Max 0.91 Min -0.34 Abs Max 0.91")
        self.assertEqual(parsed["max"], 0.91)
        self.assertEqual(parsed["min"], -0.34)
        self.assertEqual(parsed["abs_max"], 0.91)
        self.assertEqual(classify_platform_sc_text("Self-correlation Max 0.91 Min -0.34 Abs Max 0.91", parsed), "complete")

    def test_percentage_maximum_minimum_parse(self) -> None:
        parsed = parse_platform_sc_text("Self-correlation Maximum 91% Minimum -34%")
        self.assertEqual(parsed["max"], 0.91)
        self.assertEqual(parsed["min"], -0.34)
        self.assertEqual(parsed["abs_max"], 0.91)

    def test_parser_ignores_years_pass_and_time_when_labeled(self) -> None:
        parsed = parse_platform_sc_text("IS 2024 PASS 5 Correlation Maximum 0.91 Minimum -0.34 time 12:30")
        self.assertEqual(parsed["max"], 0.91)
        self.assertEqual(parsed["min"], -0.34)
        self.assertEqual(parsed["abs_max"], 0.91)

    def test_unlabeled_panel_values_are_limited_to_correlation_text(self) -> None:
        parsed = parse_platform_sc_text("Correlation testing complete values 0.22 -0.78")
        self.assertEqual(parsed["max"], 0.22)
        self.assertEqual(parsed["min"], -0.78)
        self.assertEqual(parsed["abs_max"], 0.78)

    def test_simulation_result_platform_sc_default_is_compatible(self) -> None:
        result = SimulationResult(ok=True, code="rank(close)", alpha_name="alpha")
        self.assertEqual(result.platform_sc, {})

    def test_merge_platform_sc_metrics_only_for_complete(self) -> None:
        metrics = merge_platform_sc_metrics(
            {"sharpe": 1.2},
            {"status": "complete", "max": 0.91, "min": -0.34, "abs_max": 0.91},
        )
        self.assertEqual(metrics["platform_sc_max"], 0.91)
        self.assertEqual(metrics["platform_sc_min"], -0.34)
        self.assertEqual(metrics["platform_sc_abs_max"], 0.91)
        pending = merge_platform_sc_metrics({"sharpe": 1.2}, {"status": "pending", "abs_max": 0.91})
        self.assertNotIn("platform_sc_abs_max", pending)

    def test_platform_sc_threshold_is_strictly_greater_than_point_seven(self) -> None:
        self.assertFalse(is_platform_sc_too_high({"status": "complete", "max": 0.70, "min": -0.1, "abs_max": 0.70}))
        self.assertTrue(is_platform_sc_too_high({"status": "complete", "max": 0.71, "min": -0.1, "abs_max": 0.71}))
        self.assertTrue(is_platform_sc_too_high({"status": "complete", "max": 0.2, "min": -0.71, "abs_max": 0.71}))
        self.assertEqual(apply_correlation_quality({"real_self_corr": 0.70})["correlation_quality"], "acceptable")

    def test_apply_correlation_quality_prefers_real_sc(self) -> None:
        metrics = apply_correlation_quality({"real_self_corr": 0.91, "estimated_self_corr": 0.1})
        self.assertEqual(metrics["correlation_quality"], "severe")
        self.assertEqual(metrics["submission_quality"], "blocked_by_sc")
        self.assertEqual(metrics["sc_source"], "platform")

    def test_apply_correlation_quality_falls_back_to_estimated(self) -> None:
        metrics = apply_correlation_quality({"estimated_self_corr": 0.80})
        self.assertEqual(metrics["correlation_quality"], "local_medium_risk")
        self.assertEqual(metrics["submission_quality"], "candidate_with_proxy_warning")
        self.assertEqual(metrics["sc_source"], "local_proxy")

    def test_reward_multiplier_uses_real_before_estimated(self) -> None:
        multiplier, penalty = sc_reward_multiplier({"real_self_corr": 0.90, "estimated_self_corr": 0.1})
        self.assertEqual(multiplier, 0.15)
        self.assertEqual(penalty["sc_penalty"], "severe_sc_penalty")
        self.assertFalse(strong_feedback_allowed({"real_self_corr": 0.85}))

    def test_reward_engine_applies_real_sc_penalty(self) -> None:
        engine = RewardEngine(enable_migration=False)
        plain = engine.calculate_reward(
            {"sharpe": 1.0, "fitness": 0.5, "turnover": 50.0},
            {"sharpe": 2.0, "fitness": 1.5, "turnover": 50.0},
            "rank(close)",
        )
        penalized = engine.calculate_reward(
            {"sharpe": 1.0, "fitness": 0.5, "turnover": 50.0},
            {"sharpe": 2.0, "fitness": 1.5, "turnover": 50.0, "real_self_corr": 0.90},
            "rank(close)",
        )
        self.assertAlmostEqual(penalized, plain * 0.15, places=6)
        self.assertEqual(engine.last_breakdown.metadata["platform_sc_penalty"]["sc_penalty"], "severe_sc_penalty")

    def test_candidate_pool_records_platform_sc_fields_and_legacy_rows_select(self) -> None:
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            pool = CandidatePool(Path(tmp) / "candidate_pool.json")
            with patch("wq_workflow.storage.get_storage_manager") as storage:
                storage.return_value.write_candidate_record.return_value = None
                candidate = pool.add_candidate(
                    alpha_id="a1",
                    expression="rank(close)",
                    metrics={"sharpe": 1.2, "fitness": 1.0, "real_self_corr": 0.86},
                    reward=1.0,
                    passed=True,
                )
            self.assertEqual(candidate["real_self_corr"], 0.86)
            self.assertEqual(candidate["correlation_quality"], "high_risk")
            self.assertFalse(candidate["strong_feedback_allowed"])
            self.assertIsNotNone(_selection_score({"metrics": {"sharpe": 1.0}, "reward": 1.0}))


class PlatformSelfCorrelationFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_platform_sc_complete_sets_checked_and_safe_result(self) -> None:
        ctx = SimpleNamespace(
            page=object(),
            config=WorkflowConfig(enable_platform_sc_check=True, platform_sc_timeout_seconds=5),
            alpha_name="Auto_Alpha_001",
            platform_sc={},
            platform_sc_checked=False,
        )
        with patch(
            "wq_workflow.simulate.collect_platform_sc_safely",
            AsyncMock(return_value={"status": "complete", "max": 0.91, "min": -0.34, "abs_max": 0.91}),
        ):
            result = await run_platform_sc_check_after_backtest(ctx)
        self.assertTrue(ctx.platform_sc_checked)
        self.assertEqual(result["status"], "complete")

    async def test_run_platform_sc_disabled_safe_skips(self) -> None:
        ctx = SimpleNamespace(
            page=object(),
            config=WorkflowConfig(enable_platform_sc_check=False),
            alpha_name="Auto_Alpha_001",
            platform_sc={},
            platform_sc_checked=False,
        )
        result = await run_platform_sc_check_after_backtest(ctx)
        self.assertTrue(ctx.platform_sc_checked)
        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["reason"], "disabled_by_config")


if __name__ == "__main__":
    unittest.main()
