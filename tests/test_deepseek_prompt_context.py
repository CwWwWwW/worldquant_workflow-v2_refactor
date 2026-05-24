import unittest

from wq_workflow.deepseek_client import build_improve_quality_prompt, build_structured_task_block
from wq_workflow.models import QualityReport


class DeepSeekPromptContextTests(unittest.TestCase):
    def test_structured_task_block_contains_required_fields(self) -> None:
        block = build_structured_task_block(
            {
                "current_expression": "rank(ts_mean(close, 20))",
                "current_metrics": {"sharpe": 1.0, "fitness": 0.5, "turnover": 70},
                "mutation_goal": "Reduce turnover",
                "allowed_mutations": ["add_decay", "reduce_turnover"],
                "forbidden_mutations": ["replace_signal"],
                "historical_successful_mutations": [],
                "recent_failed_patterns": [],
                "complexity": {"operator_count": 2},
                "complexity_limit": {"max_operator_count": 4},
            }
        )

        for label in [
            "Current expression",
            "Current AST summary",
            "Current Strategy",
            "Current metrics",
            "Mutation goal",
            "Allowed Structural Mutations",
            "Forbidden",
            "Operator Graph Recommendations",
            "Similarity constraints",
            "Recent failed patterns",
            "Complexity limits",
            "Recent successful lineages",
            "Diversity requirements",
            "Output format constraints",
        ]:
            self.assertIn(label, block)
        self.assertIn("- add_decay", block)

    def test_empty_allowed_mutations_get_default(self) -> None:
        block = build_structured_task_block({"current_expression": "rank(close)", "allowed_mutations": []})

        self.assertIn("- replace_window", block)

    def test_improve_quality_prompt_includes_structured_context(self) -> None:
        prompt = build_improve_quality_prompt(
            "rank(close)",
            QualityReport(False, "needs_improvement", metrics={"sharpe": 0.4}),
            "IS Summary Sharpe 0.4",
            {"current_expression": "rank(close)", "allowed_mutations": ["simplify_expression"]},
        )

        self.assertIn("Structured Alpha Optimization Task", prompt)
        self.assertIn("- simplify_expression", prompt)


if __name__ == "__main__":
    unittest.main()
