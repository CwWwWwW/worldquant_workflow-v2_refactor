import json
import tempfile
import unittest
from pathlib import Path

from wq_workflow.candidate_pool import CandidatePool
from wq_workflow.core.ast import serialize_ast
from wq_workflow.core.parser import ExpressionParser
from wq_workflow.fast_expression import validate_fast_expression
from wq_workflow.paths import append_csv, ensure_csv
from wq_workflow.v2_engine import (
    AdaptiveMutationScheduler,
    FamilyRouter,
    RegimeMutator,
    build_behavior_fingerprint,
    compute_behavior_similarity,
    estimate_self_corr,
)


class V2ParserAndValidationTests(unittest.TestCase):
    def test_parser_round_trips_comparison_in_trade_when(self) -> None:
        ast = ExpressionParser().parse("trade_when(volume > adv20, rank(close), -1)")

        self.assertEqual(serialize_ast(ast), "trade_when(volume > adv20, rank(close), -1)")

    def test_trade_when_flag_controls_validation(self) -> None:
        code = "trade_when(volume > adv20, returns, -1)"

        self.assertEqual("", validate_fast_expression(code, enable_v2_engine=True))
        self.assertIn("trade_when", validate_fast_expression(code, enable_v2_engine=False))


class V2BehaviorTests(unittest.TestCase):
    def test_behavior_fingerprint_extracts_core_fields(self) -> None:
        fp = build_behavior_fingerprint("trade_when(volume > adv20, group_neutralize(ts_delta(close, 5), industry), -1)")

        self.assertTrue(fp["trade_when"])
        self.assertEqual(fp["group_ops"], 1)
        self.assertEqual(fp["delay_family"], "delta")
        self.assertIn(fp["family"], {"event", "hybrid", "momentum"})

    def test_family_router_classifies_group_alpha(self) -> None:
        family = FamilyRouter().classify("group_neutralize(rank(close), sector)")

        self.assertEqual(family, "group")

    def test_behavior_similarity_scores_related_higher(self) -> None:
        left = build_behavior_fingerprint("trade_when(volume > adv20, rank(close), -1)")
        close = build_behavior_fingerprint("trade_when(rank(cap) > 0.2, rank(vwap), -1)")
        far = build_behavior_fingerprint("group_neutralize(ts_std_dev(returns, 20), sector)")

        self.assertGreater(compute_behavior_similarity(left, close), compute_behavior_similarity(left, far))

    def test_sc_proxy_uses_behavior_similarity(self) -> None:
        estimate = estimate_self_corr(
            "trade_when(volume > adv20, rank(vwap), -1)",
            [{"alpha_id": "a1", "expression": "trade_when(volume > adv20, rank(close), -1)"}],
            metrics={"fitness": 0.5},
        )

        self.assertEqual(estimate["nearest_alpha_id"], "a1")
        self.assertGreater(estimate["estimated_self_corr"], 0.5)
        self.assertEqual(estimate["similarity_limit"], 0.75)

    def test_scheduler_keeps_high_fitness_similarity_inheritance(self) -> None:
        schedule = AdaptiveMutationScheduler().schedule(
            {"fitness": 1.2, "turnover": 20},
            build_behavior_fingerprint("rank(close)"),
            {"estimated_self_corr": 0.8},
            lineage_depth=4,
        )

        self.assertEqual(schedule.similarity_limit, 0.85)
        self.assertIn("trade_when_mutation", schedule.recommended_mutations)

    def test_regime_mutator_generates_valid_trade_when(self) -> None:
        candidates = RegimeMutator().generate("rank(close)", limit=3)

        self.assertTrue(any(candidate.mutation_type == "trade_when_mutation" for candidate in candidates))
        self.assertTrue(all(validate_fast_expression(candidate.expression, enable_v2_engine=True) == "" for candidate in candidates))


class V2CompatibilityTests(unittest.TestCase):
    def test_candidate_pool_appends_optional_v2_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pool = CandidatePool(Path(tmp) / "candidate_pool.json")
            row = pool.add_candidate(
                alpha_id="a1",
                expression="trade_when(volume > adv20, rank(close), -1)",
                metrics={"fitness": 1.1},
            )

            self.assertEqual(row["behavior_family"], row["behavior_fingerprint"]["family"])
            self.assertIn("estimated_self_corr", row)

    def test_csv_header_extension_preserves_old_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "library.csv"
            path.write_text("alpha_id,code\nold,rank(close)\n", encoding="utf-8")

            fields = ensure_csv(path, ["alpha_id", "code", "behavior_family"])
            append_csv(path, ["alpha_id", "code", "behavior_family"], {"alpha_id": "new", "code": "rank(vwap)", "behavior_family": "momentum"})

            text = path.read_text(encoding="utf-8")
            self.assertIn("old,rank(close),", text)
            self.assertIn("new,rank(vwap),momentum", text)
            self.assertIn("behavior_family", fields)

    def test_legacy_json_rows_without_v2_fields_still_estimate(self) -> None:
        estimate = estimate_self_corr("rank(vwap)", [{"alpha_id": "legacy", "expression": "rank(close)"}])

        self.assertEqual(estimate["nearest_alpha_id"], "legacy")
        self.assertIsInstance(json.dumps(estimate["behavior_fingerprint"]), str)


if __name__ == "__main__":
    unittest.main()
