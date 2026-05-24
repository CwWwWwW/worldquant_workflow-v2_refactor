import unittest

from wq_workflow.core.ast import serialize_ast
from wq_workflow.core.evolution_tree import EvolutionNode, EvolutionTree
from wq_workflow.core.mutation_constraints import MutationConstraints
from wq_workflow.core.parser import ExpressionParser
from wq_workflow.core.semantic_similarity import SemanticSimilarity
from wq_workflow.core.strategy_engine import Strategy, StrategyEngine, StrategyType
from wq_workflow.core.structural_mutator import StructuralMutator


class ParserSerializerTests(unittest.TestCase):
    def test_round_trip_nested_expression(self) -> None:
        ast = ExpressionParser().parse("rank(ts_mean(close,20))")

        self.assertEqual(serialize_ast(ast), "rank(ts_mean(close, 20))")
        self.assertEqual(ast.to_dict()["children"][0]["parameters"], {"window": 20})

    def test_named_parameter_and_assignments(self) -> None:
        code = 'signal1 = rank(close)\nbucket(signal1, range="0.1,1,0.1")'
        ast = ExpressionParser().parse(code)

        self.assertEqual(ast.type, "program")
        self.assertIn('range="0.1,1,0.1"', serialize_ast(ast))


class StructuralMutationTests(unittest.TestCase):
    def test_wrap_node_generates_decay(self) -> None:
        ast = ExpressionParser().parse("rank(close)")
        candidates = StructuralMutator().wrap_node(ast, "ts_decay_exp_window", window=8)

        self.assertTrue(any("ts_decay_exp_window(close, 8)" in item.expression for item in candidates))

    def test_constraints_reject_redundant_rank(self) -> None:
        ast = ExpressionParser().parse("rank(rank(close))")
        result = MutationConstraints().validate(ast)

        self.assertFalse(result.passed)
        self.assertIn("rank", result.reason)

    def test_semantic_safe_field_swap(self) -> None:
        ast = ExpressionParser().parse("rank(close)")
        mutator = StructuralMutator()

        self.assertIsNotNone(mutator.replace_field(ast, "close", "vwap"))
        self.assertIsNone(mutator.replace_field(ast, "close", "adv20"))


class SemanticSimilarityTests(unittest.TestCase):
    def test_structurally_similar_expressions_score_high(self) -> None:
        parser = ExpressionParser()
        left = parser.parse("rank(ts_mean(close, 20))")
        right = parser.parse("rank(ts_mean(vwap, 20))")

        self.assertGreater(SemanticSimilarity().similarity(left, right), 0.85)

    def test_different_structure_scores_lower(self) -> None:
        parser = ExpressionParser()
        left = parser.parse("rank(ts_mean(close, 20))")
        right = parser.parse("group_neutralize(ts_corr(volume, returns, 126), sector)")

        self.assertLess(SemanticSimilarity().similarity(left, right), 0.85)


class EvolutionSearchTests(unittest.TestCase):
    def test_beam_search_returns_multiple_branches(self) -> None:
        parser = ExpressionParser()
        parents = [
            EvolutionNode("rank(close)", parser.parse("rank(close)"), reward=1.0),
            EvolutionNode("scale(ts_mean(volume, 20))", parser.parse("scale(ts_mean(volume, 20))"), reward=0.2),
        ]
        strategy = Strategy(StrategyType.DIVERSITY_EXPANSION, ["replace_operator", "wrap_node", "replace_window"])

        children = EvolutionTree().expand(parents, beam_width=5, strategy=strategy)

        self.assertGreaterEqual(len(children), 2)
        self.assertGreaterEqual(len({child.parent.expression for child in children if child.parent}), 2)


class StrategyEngineTests(unittest.TestCase):
    def test_turnover_strategy(self) -> None:
        strategy = StrategyEngine().choose({"turnover": 80, "sharpe": 1.2, "fitness": 1.1})

        self.assertEqual(strategy.name, StrategyType.TURNOVER_REDUCTION)
        self.assertIn("wrap_node", strategy.allowed_mutations)


if __name__ == "__main__":
    unittest.main()
