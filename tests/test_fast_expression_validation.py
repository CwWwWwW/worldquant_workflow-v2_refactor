import unittest

from wq_workflow.fast_expression import validate_fast_expression


class FastExpressionValidationTests(unittest.TestCase):
    def test_blocks_current_unknown_operators(self) -> None:
        for code in [
            "group_normalize(returns, sector)",
            "ts_entropy(volume, 20)",
        ]:
            with self.subTest(code=code):
                self.assertTrue(validate_fast_expression(code))

    def test_blocks_unit_risky_group_mean_weight(self) -> None:
        code = "group_mean(returns, cap, market)"

        self.assertIn("group_mean", validate_fast_expression(code))

    def test_allows_safe_group_mean_weight(self) -> None:
        code = "group_mean(returns, 1, market)"

        self.assertEqual("", validate_fast_expression(code))

    def test_allows_hump_operator_for_controlled_turnover_mutation(self) -> None:
        code = "hump(rank(close), 0.01)"

        self.assertEqual("", validate_fast_expression(code))

    def test_allows_alpha_signal_and_final_signal_variables(self) -> None:
        code = """
        market_return = group_mean(returns, 1, market)
        alpha_signal = -1 * (returns - market_return)
        final_signal = group_neutralize(alpha_signal, bucket(rank(cap), range='0.1,1,0.1'))
        final_signal
        """

        self.assertEqual("", validate_fast_expression(code))

    def test_blocks_trade_when_when_v2_disabled(self) -> None:
        code = "trade_when(volume > ts_mean(volume, 20), returns, -1)"

        self.assertIn("trade_when", validate_fast_expression(code, enable_v2_engine=False))

    def test_allows_trade_when_when_v2_enabled(self) -> None:
        code = "trade_when(volume > adv20, returns, -1)"

        self.assertEqual("", validate_fast_expression(code, enable_v2_engine=True))

    def test_blocks_reserved_adv_variable(self) -> None:
        code = "adv20 = ts_mean(volume, 20);\nrank(volume / adv20)"

        self.assertTrue(validate_fast_expression(code))

    def test_blocks_reserved_alpha_and_group_variables(self) -> None:
        for code in [
            "alpha = returns\nalpha",
            "group = bucket(rank(cap), range='0.1,1,0.1')\ngroup_neutralize(returns, group)",
        ]:
            with self.subTest(code=code):
                self.assertTrue(validate_fast_expression(code))


if __name__ == "__main__":
    unittest.main()
