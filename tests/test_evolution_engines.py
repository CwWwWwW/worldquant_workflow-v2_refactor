import tempfile
import unittest
import math
from pathlib import Path
from types import SimpleNamespace

from wq_workflow.candidate_pool import CandidatePool
from wq_workflow.core.evolution import AlphaSimulator, ASTCrossover, ASTEvolutionEngine, EvolutionPolicy, EvolutionScorer, PopulationEngine
from wq_workflow.memory_manager import EvolutionMemory
from wq_workflow.mutation_engine import (
    MutationPlanner,
    complexity_score,
    dynamic_complexity_limit,
    normalize_turnover,
    validate_controlled_expression,
)
from wq_workflow.reward_engine import RewardEngine
from wq_workflow.storage.evolution_repository import EvolutionDBRepository
from wq_workflow.storage.schema import initialize_schema
from wq_workflow.storage.sqlite_store import connect_db


class RewardEngineTests(unittest.TestCase):
    def test_reward_formula_normalizes_turnover_percent(self) -> None:
        reward = RewardEngine().calculate_reward(
            {"sharpe": 1.0, "fitness": 0.5, "turnover": 0.60},
            {"sharpe": 1.2, "fitness": 0.7, "turnover": 50.0},
            "rank(ts_mean(close, 20))",
        )

        self.assertAlmostEqual(reward, 0.18, places=6)

    def test_hard_penalties_apply(self) -> None:
        reward = RewardEngine(expression_length_limit=10, operator_count_limit=1).calculate_reward(
            {"sharpe": 1.0, "fitness": 1.0, "turnover": 70},
            {"sharpe": 1.0, "fitness": 1.0, "turnover": 80},
            "rank(ts_mean(close, 20))",
        )

        self.assertLess(reward, -0.9)

    def test_non_finite_metrics_are_clamped(self) -> None:
        reward = RewardEngine(enable_migration=False).calculate_reward(
            {"sharpe": "nan", "fitness": "inf", "turnover": "-inf"},
            {"sharpe": float("inf"), "fitness": float("nan"), "turnover": 0.6},
            "rank(close)",
        )

        self.assertTrue(math.isfinite(reward))
        self.assertGreaterEqual(reward, -10.0)
        self.assertLessEqual(reward, 10.0)


class ComplexityTests(unittest.TestCase):
    def test_complexity_score_counts_core_dimensions(self) -> None:
        score = complexity_score("rank(group_neutralize(ts_mean(close, 20), industry))")

        self.assertEqual(score["operator_count"], 3)
        self.assertEqual(score["ts_operator_count"], 1)
        self.assertEqual(score["neutralization_layers"], 1)
        self.assertGreaterEqual(score["nesting_depth"], 3)

    def test_dynamic_limit_keeps_low_sharpe_operator_cap(self) -> None:
        limit = dynamic_complexity_limit({"sharpe": 0.4, "turnover": 20}, "rank(ts_mean(close, 20))")

        self.assertLessEqual(limit["max_operator_count"], 18)
        self.assertGreaterEqual(limit["max_operator_count"], limit["current_operator_count"])


class MutationPlannerTests(unittest.TestCase):
    def test_high_turnover_plan(self) -> None:
        plan = MutationPlanner().plan({"turnover": 70, "sharpe": 1.2, "fitness": 1.1}, "rank(close)", "")

        self.assertIn("add_decay", plan.allowed_mutations)
        self.assertIn("wrap_node", plan.allowed_structural_mutations)
        self.assertEqual(plan.current_strategy, "turnover_reduction")
        self.assertIn("reduce_turnover", plan.allowed_mutations)
        self.assertIn("replace_signal", plan.forbidden_mutations)

    def test_low_fitness_with_good_sharpe_plan(self) -> None:
        plan = MutationPlanner().plan({"turnover": 20, "sharpe": 1.1, "fitness": 0.5}, "rank(close)", "")

        self.assertIn("add_neutralization", plan.allowed_mutations)
        self.assertIn("bucket", plan.allowed_mutations)

    def test_operator_misuse_plan(self) -> None:
        plan = MutationPlanner().plan({}, "bad(close)", 'unknown operator "bad"')

        self.assertIn("simplify_expression", plan.allowed_mutations)
        self.assertIn("new_unknown_operator", plan.forbidden_mutations)

    def test_turnover_normalization(self) -> None:
        self.assertEqual(normalize_turnover(0.7), 70.0)
        self.assertEqual(normalize_turnover(70.0), 70.0)

    def test_controlled_validation_rejects_unknown_operator(self) -> None:
        plan = MutationPlanner().plan({"turnover": 70}, "rank(close)", "turnover high")

        self.assertIn("bad", validate_controlled_expression("rank(close)", "bad(close)", plan).lower())

    def test_controlled_validation_rejects_forbidden_new_field(self) -> None:
        plan = MutationPlanner().plan({"turnover": 70}, "rank(close)", "turnover high")

        self.assertIn("new data fields", validate_controlled_expression("rank(close)", "rank(vwap)", plan))


class EvolutionMemoryTests(unittest.TestCase):
    def test_save_mutation_and_statistics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = EvolutionMemory(
                lineage_file=root / "lineage.json",
                failures_file=root / "failures.json",
                statistics_file=root / "stats.json",
            )

            memory.save_mutation(
                alpha_id="a2",
                parent_id="a1",
                expression_before="rank(close)",
                expression_after="rank(ts_mean(close, 20))",
                mutation_type="add_decay",
                metrics_before={"sharpe": 1.0, "fitness": 0.4, "turnover": 80},
                metrics_after={"sharpe": 1.2, "fitness": 0.5, "turnover": 60},
                delta={"sharpe": 0.2, "fitness": 0.1, "turnover": -20},
                passed=True,
                reward=0.1,
            )

            stats = memory.get_operator_statistics()
            self.assertEqual(stats["add_decay"]["count"], 1)
            self.assertEqual(stats["add_decay"]["avg_turnover_reduction"], 20)
            self.assertEqual(len(memory.get_best_mutations()), 1)

    def test_failure_pattern_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = EvolutionMemory(
                lineage_file=root / "lineage.json",
                failures_file=root / "failures.json",
                statistics_file=root / "stats.json",
            )
            memory.save_failure_pattern(error_type="operator misuse", expression="bad(close)", root_cause="unknown")

            self.assertEqual(memory.get_failure_patterns()[0]["error_type"], "operator misuse")


class CandidatePoolTests(unittest.TestCase):
    def test_pool_trims_to_top_20_and_selects_parent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pool = CandidatePool(Path(tmp) / "pool.json", max_size=20)
            for index in range(25):
                pool.add_candidate(
                    alpha_id=f"a{index}",
                    expression=f"rank(ts_mean(close, {index + 2}))",
                    metrics={"sharpe": float(index), "fitness": float(index) / 10},
                    reward=float(index) / 100,
                )

            self.assertEqual(len(pool.get_top_sharpe(25)), 20)
            self.assertEqual(pool.select_next_parent()["alpha_id"], "a24")

    def test_diverse_candidates_have_score(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pool = CandidatePool(Path(tmp) / "pool.json", max_size=20)
            pool.add_candidate(alpha_id="a1", expression="rank(close)", metrics={"sharpe": 1})
            pool.add_candidate(alpha_id="a2", expression="rank(ts_mean(volume, 20))", metrics={"sharpe": 1})

            diverse = pool.get_diverse_candidates(2)
            self.assertIn("diversity_score", diverse[0])
            self.assertIn("semantic_signature", diverse[0])

    def test_ast_duplicate_replaces_existing_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pool = CandidatePool(Path(tmp) / "pool.json", max_size=20)
            pool.add_candidate(alpha_id="a1", expression="rank(close)", metrics={"sharpe": 1}, reward=1.0)
            pool.add_candidate(alpha_id="a2", expression="rank( close )", metrics={"sharpe": 2}, reward=2.0)

            rows = pool.get_top_sharpe(10)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["alpha_id"], "a2")


class DBBackedEvolutionEngineTests(unittest.TestCase):
    def test_population_bootstrap_and_tournament_selection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            conn = connect_db(root / "workflow.db")
            try:
                initialize_schema(conn)
                pool = CandidatePool(root / "pool.json", max_size=20)
                pool.add_candidate(alpha_id="a1", expression="rank(close)", metrics={"sharpe": 1.0}, reward=0.1)
                pool.add_candidate(alpha_id="a2", expression="rank(ts_mean(close, 20))", metrics={"sharpe": 2.0}, reward=0.4)
                repo = EvolutionDBRepository(conn)
                engine = PopulationEngine(repository=repo, config=SimpleNamespace(population_size=10, population_tournament_k=2))

                self.assertGreaterEqual(engine.bootstrap_from_legacy(candidate_pool=pool), 2)
                parent = engine.tournament_selection(engine.get_population())

                self.assertIsNotNone(parent)
                self.assertIn("survival_score", parent)
            finally:
                conn.close()

    def test_policy_action_update_persists_and_fallback_without_db(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            conn = connect_db(Path(tmp) / "workflow.db")
            try:
                initialize_schema(conn)
                repo = EvolutionDBRepository(conn)
                policy = EvolutionPolicy(repository=repo, config=SimpleNamespace(policy_learning_rate=0.5, policy_min_weight=0.15, policy_max_weight=5.0))
                policy.update_after_result("mutation", "add_decay", 1.0, True, {"mutation_goal": "turnover high"})

                self.assertGreater(repo.get_policy_weights("mutation", policy.context_key({"mutation_goal": "turnover high"}))["add_decay"], 1.0)
                action, weights = EvolutionPolicy(repository=None).select_action("mutation", ["add_decay"], {})
                self.assertEqual(action, "add_decay")
                self.assertEqual(weights["add_decay"], 1.0)
            finally:
                conn.close()

    def test_crossover_and_simulator_experimental_gate(self) -> None:
        child = ASTCrossover().maybe_crossover(
            {"alpha_id": "p1", "expression": "rank(close)", "reward": 0.1},
            {"alpha_id": "p2", "expression": "rank(volume)", "reward": 0.2},
        )
        self.assertIsNotNone(child)
        self.assertEqual(child["parent_ids"], ["p1", "p2"])

        self.assertIsNone(
            ASTCrossover().maybe_crossover(
                {"alpha_id": "p1", "expression": "bad("},
                {"alpha_id": "p2", "expression": "rank(volume)"},
            )
        )

        simulator = AlphaSimulator(skip_threshold=0.95, skip_enabled=True)
        candidate = {
            "alpha_id": "a1",
            "expression": "rank(close)",
            "parent_reward": 0.0,
            "candidate_source": "mutation",
            "is_pending_candidate": True,
        }
        self.assertFalse(simulator.should_skip(candidate, experimental=False)[0])
        self.assertTrue(simulator.should_skip(candidate, experimental=True)[0])

    def test_crossover_random_subtree_varies_with_different_seed(self) -> None:
        expr_a = "rank(ts_mean(close, 20) + ts_std_dev(volume, 10))"
        expr_b = "rank(ts_rank(open, 5) / ts_sum(close, 30))"
        seen = set()
        for seed in range(8):
            result = ASTCrossover(
                config=SimpleNamespace(max_crossover_attempts=1, crossover_random_subtree_selection=True),
                random_seed=seed,
            ).crossover(expr_a, expr_b)
            self.assertTrue(result.ok)
            seen.add((tuple(result.metadata.get("path_a") or []), tuple(result.metadata.get("path_b") or [])))
        self.assertGreater(len(seen), 1)

    def test_crossover_random_subtree_deterministic_with_seed(self) -> None:
        expr_a = "rank(ts_mean(close, 20) + ts_std_dev(volume, 10))"
        expr_b = "rank(ts_rank(open, 5) / ts_sum(close, 30))"
        cfg_obj = SimpleNamespace(max_crossover_attempts=3, crossover_random_subtree_selection=True)
        first = ASTCrossover(config=cfg_obj, random_seed=42).crossover(expr_a, expr_b)
        second = ASTCrossover(config=cfg_obj, random_seed=42).crossover(expr_a, expr_b)
        self.assertEqual(first.expression, second.expression)
        self.assertEqual(first.metadata.get("path_a"), second.metadata.get("path_a"))
        self.assertEqual(first.metadata.get("path_b"), second.metadata.get("path_b"))

    def test_crossover_validation_still_blocks_complexity(self) -> None:
        engine = ASTEvolutionEngine(max_operator_count=0)
        result = ASTCrossover(
            engine=engine,
            config=SimpleNamespace(max_crossover_attempts=3, crossover_random_subtree_selection=True),
            random_seed=1,
        ).crossover("rank(ts_mean(close, 20))", "rank(ts_mean(volume, 10))")
        self.assertFalse(result.ok)
        self.assertTrue(result.rolled_back)

    def test_evolution_scorer_does_not_overwrite_reward(self) -> None:
        candidate = {"alpha_id": "a1", "expression": "rank(close)", "reward": 2.0, "metrics": {"sharpe": 1.0}}
        overlay = EvolutionScorer().score_overlay(candidate, population=[], lineage_history=[])

        self.assertEqual(candidate["reward"], 2.0)
        self.assertIn("survival_score", overlay)
        self.assertNotIn("reward", overlay)


if __name__ == "__main__":
    unittest.main()
