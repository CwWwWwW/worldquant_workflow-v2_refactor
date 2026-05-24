import json
import tempfile
import unittest
from pathlib import Path

from wq_workflow.candidate_pool import CandidatePool
from wq_workflow.core.evolution import (
    ASTCrossover,
    ASTEvolutionEngine,
    AlphaSimulator,
    PopulationEngine,
    SidecarContract,
    suggest_mutation_weights,
)
from wq_workflow.mutation_engine import MutationPlanner


class SidecarComplianceTests(unittest.TestCase):
    def test_mutation_planner_ignores_weight_hint_when_flag_off(self) -> None:
        planner = MutationPlanner()
        metrics = {"turnover": 70, "sharpe": 1.2, "fitness": 1.1}
        baseline = planner.plan(metrics, "rank(close)", "turnover high")
        hinted = planner.plan(metrics, "rank(close)", "turnover high", weight_hint={"replace_signal": 99.0})

        self.assertEqual(hinted.allowed_mutations, baseline.allowed_mutations)
        self.assertEqual(hinted.allowed_structural_mutations, baseline.allowed_structural_mutations)
        self.assertEqual(hinted.priority, baseline.priority)
        self.assertNotIn("mutation_weights_hint", hinted.to_dict())

        enabled = planner.plan(
            metrics,
            "rank(close)",
            "turnover high",
            weight_hint={"add_decay": 2.5, "replace_signal": 99.0},
            enable_evolution_policy=True,
        )
        self.assertEqual(enabled.allowed_mutations, baseline.allowed_mutations)
        self.assertEqual(enabled.allowed_structural_mutations, baseline.allowed_structural_mutations)
        self.assertEqual(enabled.priority, baseline.priority)
        self.assertEqual(enabled.to_dict()["mutation_weights_hint"]["add_decay"], 2.5)

    def test_evolution_policy_returns_hint_only(self) -> None:
        history = [
            {"mutation_type": "add_decay", "reward": 1.0, "passed": True},
            {"mutation_type": "replace_signal", "reward": -0.5, "passed": False},
        ]

        hint = suggest_mutation_weights(history)

        self.assertGreater(hint["add_decay"], hint["replace_signal"])
        self.assertIn("change_window", hint)

    def test_alpha_simulator_observes_without_skip_contract(self) -> None:
        result = AlphaSimulator(low_confidence_threshold=0.9).evaluate(
            {
                "expression": "rank(ts_mean(close, 20))",
                "metrics": {"turnover": 80},
                "estimated_self_corr": 0.9,
            }
        )

        self.assertIn("simulator_score", result)
        self.assertTrue(result["low_confidence"])
        self.assertTrue(str(result["recommendation"]).startswith("continue_backtest"))
        self.assertNotIn("skip", result)
        self.assertEqual(result["authority"], "observer_only")

    def test_population_overlay_without_repository_does_not_touch_candidate_pool(self) -> None:
        self.assertTrue(hasattr(PopulationEngine, "select_parent"))
        self.assertTrue(hasattr(PopulationEngine, "tournament_selection"))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "candidate_pool.json"
            pool = CandidatePool(path)
            candidate = pool.add_candidate(
                alpha_id="a1",
                expression="rank(close)",
                metrics={"sharpe": 1.0, "fitness": 1.0, "turnover": 20},
                reward=1.0,
            )
            before = path.read_text(encoding="utf-8")
            overlay = PopulationEngine().score_overlay(candidate, population=pool.get_top_sharpe(10), lineage_history=[])
            after = path.read_text(encoding="utf-8")

            self.assertIn("survival_score", overlay)
            self.assertEqual(overlay["authority"], "advisory_only")
            self.assertEqual(overlay["decision_authority"], "none")
            self.assertIsNone(PopulationEngine().select_parent())
            self.assertEqual(before, after)

    def test_sidecar_contract_records_annotations_without_flow_decision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "sidecar.jsonl"
            sidecar = SidecarContract(log_path=log_path)
            population = [{"alpha_id": "p1", "expression": "rank(close)", "reward": 1.0}]
            before_count = len(population)

            pre = sidecar.pre_backtest(
                {"alpha_id": "a1", "expression": "rank(volume)", "metrics": {"turnover": 10}},
                population=population,
                lineage_history=[],
            )
            post = sidecar.post_backtest(
                {"alpha_id": "a1", "expression": "rank(volume)"},
                metrics={"sharpe": 1.1},
                quality_passed=False,
            )

            self.assertEqual(len(population), before_count)
            self.assertEqual(pre["decision_authority"], "none")
            self.assertEqual(post["decision_authority"], "none")
            rows = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual([row["phase"] for row in rows], ["pre_backtest", "post_backtest"])

    def test_ast_crossover_failure_rolls_back_and_writes_side_failure_log_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            failure_log = Path(tmp) / "ast_failures.jsonl"
            engine = ASTEvolutionEngine(failure_log_path=failure_log, max_expression_length=1)
            result = ASTCrossover(engine).crossover("rank(close)", "rank(volume)")

            self.assertFalse(result.ok)
            self.assertTrue(result.rolled_back)
            self.assertEqual(result.expression, "rank(close)")
            self.assertTrue(failure_log.exists())
            payload = json.loads(failure_log.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(payload["operation"], "crossover")
            self.assertFalse((Path(tmp) / "alpha_lineage.json").exists())


if __name__ == "__main__":
    unittest.main()
