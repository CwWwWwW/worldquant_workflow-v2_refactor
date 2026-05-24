import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from log_manager.exporter import discover_log_files
from log_manager.importer import _merge_json_lists
from wq_workflow.core.insight import InsightClusterer, InsightExtractor, InsightInjector, InsightManager, InsightScorer
from wq_workflow.core.insight.models import ResearchInsight
from wq_workflow.deepseek_client import build_structured_task_block


class ResearchInsightLayerTests(unittest.TestCase):
    def test_extractor_reads_legacy_lineage_and_wrapped_survival(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_insight_inputs(root)

            samples = InsightExtractor(root).extract_all()

            lineage = [sample for sample in samples if sample.alpha_id == "alpha-1:2"][0]
            self.assertIn("ts_mean", lineage.operators)
            self.assertEqual(lineage.family, "mean_reversion")
            self.assertEqual(lineage.survival_rounds, 7)

    def test_clusterer_builds_rule_clusters(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_insight_inputs(root)
            samples = InsightExtractor(root).extract_all()

            clusters = InsightClusterer().cluster(samples)
            types = {cluster.type for cluster in clusters}

            self.assertIn("operator_combo", types)
            self.assertIn("reward_pattern", types)
            self.assertIn("failure_pattern", types)
            self.assertIn("family_pattern", types)

    def test_scorer_penalizes_contradiction_and_decay(self) -> None:
        fresh = _insight("Fresh signal", support=10, contradiction=0, rounds=[98, 100])
        stale = _insight("Stale signal", support=10, contradiction=8, rounds=[1])

        scored_fresh = InsightScorer().score(fresh, current_round=100)
        scored_stale = InsightScorer().score(stale, current_round=320)

        self.assertGreater(scored_fresh.confidence, scored_stale.confidence)
        self.assertLess(scored_stale.decay_score, scored_fresh.decay_score)

    def test_manager_merge_prune_and_schema_extension(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = InsightManager(root=Path(tmp))
            existing = _insight("Short-window mean reversion works with decay.", support=4, contradiction=0)
            existing.extra["future_field"] = {"kept": True}
            incoming = _insight("Short-window mean reversion works with decay.", support=8, contradiction=1)
            bad = _insight("weak", support=1, contradiction=0)
            bad.confidence = 0.1

            merged = manager.merge_insights([existing], [incoming, bad])
            pruned = manager.prune_stale(merged)

            self.assertEqual(len([item for item in merged if "mean reversion" in item.summary]), 1)
            self.assertTrue(merged[0].extra["future_field"]["kept"])
            self.assertNotIn("weak", [item.summary for item in pruned])

    def test_injector_limits_top_k_and_prompt_size(self) -> None:
        insights = [
            _insight("Use decay with rank to control turnover in mean reversion.", confidence=0.9, operators=["rank", "ts_mean"]),
            _insight("Avoid nested vector operators when operator misuse repeats.", confidence=0.8, operators=["vec_avg"]),
            _insight("Group neutralization can improve diversification.", confidence=0.7, operators=["group_neutralize"]),
        ]
        context = {
            "current_expression": "rank(ts_mean(close, 6))",
            "behavior_family": "mean_reversion",
            "mutation_goal": "reduce turnover",
        }

        selected = InsightInjector().top_k(insights, context, k=2)
        block = InsightInjector().format_for_prompt(selected, max_chars=160)

        self.assertEqual(len(selected), 2)
        self.assertLessEqual(len(block), 160)
        self.assertIn("decay", block)

    def test_prompt_contains_research_insights_and_default_fallback(self) -> None:
        with_insight = build_structured_task_block(
            {
                "current_expression": "rank(close)",
                "allowed_mutations": ["replace_window"],
                "research_insights": "- [0.82] Use short decay windows for turnover control.",
            }
        )
        no_insight = build_structured_task_block({"current_expression": "rank(close)"})

        self.assertIn("Long-term Research Insights", with_insight)
        self.assertIn("short decay", with_insight)
        self.assertIn("No long-term research insight distilled yet", no_insight)

    def test_manager_distill_if_due_fallback_is_offline_safe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_insight_inputs(root)
            manager = InsightManager(root=root)

            generated = asyncio.run(manager.distill_if_due(interval=1, min_samples=1, force=True))

            self.assertTrue(generated)
            saved = json.loads((root / "memory" / "insights" / "research_insights.json").read_text(encoding="utf-8"))
            self.assertTrue(saved)

    def test_export_discovery_and_import_identity_support_insights(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_insight_inputs(root)
            insights_dir = root / "memory" / "insights"
            insights_dir.mkdir(parents=True, exist_ok=True)
            (insights_dir / "research_insights.json").write_text(
                json.dumps([{"id": "insight-1", "summary": "x"}]),
                encoding="utf-8",
            )
            (insights_dir / "insight_state.json").write_text("{}", encoding="utf-8")

            specs = discover_log_files(root)
            rels = {spec.relative_path: spec.schema_version for spec in specs}
            merged = _merge_json_lists([{"id": "insight-1", "summary": "old"}], [{"id": "insight-1", "summary": "new"}])

            self.assertEqual(rels["memory/insights/research_insights.json"], "research_insight_v1")
            self.assertEqual(rels["memory/insights/insight_state.json"], "insight_state_v1")
            self.assertEqual(len(merged), 1)


def _seed_insight_inputs(root: Path) -> None:
    (root / "memory" / "evolution").mkdir(parents=True)
    (root / "memory" / "statistics").mkdir(parents=True)
    (root / "memory" / "failure_patterns").mkdir(parents=True)
    (root / "memory" / "insights").mkdir(parents=True)
    (root / "memory" / "evolution" / "alpha_lineage.json").write_text(
        json.dumps(
            [
                {
                    "alpha_id": "alpha-1:2",
                    "expression_after": "rank(ts_mean(close, 6))",
                    "metrics_after": {"sharpe": 1.4, "fitness": 1.1, "turnover": 40},
                    "reward": 0.8,
                    "passed": True,
                    "quality_passed": True,
                    "timestamp": "2026-05-08T10:00:00",
                    "behavior_family": "mean_reversion",
                },
                {
                    "alpha_id": "alpha-2:3",
                    "expression_after": "rank(ts_mean(returns, 8))",
                    "metrics_after": {"sharpe": 1.2, "fitness": 1.0, "turnover": 45},
                    "reward": 0.4,
                    "passed": True,
                    "timestamp": "2026-05-08T10:01:00",
                    "behavior_family": "mean_reversion",
                },
                {
                    "alpha_id": "alpha-3:4",
                    "expression_after": "vec_avg(close)",
                    "metrics_after": {},
                    "reward": -0.5,
                    "passed": False,
                    "failure_reason": "Invalid number of inputs",
                    "timestamp": "2026-05-08T10:02:00",
                },
            ]
        ),
        encoding="utf-8",
    )
    (root / "memory" / "evolution" / "candidate_pool.json").write_text(
        json.dumps(
            [
                {
                    "alpha_id": "alpha-4:5",
                    "expression": "group_neutralize(rank(ts_mean(close, 10)), industry)",
                    "metrics": {"sharpe": 1.5, "fitness": 1.2, "turnover": 30},
                    "reward": 0.6,
                    "passed": True,
                    "behavior_family": "mean_reversion",
                }
            ]
        ),
        encoding="utf-8",
    )
    (root / "memory" / "evolution" / "survival_memory.json").write_text(
        json.dumps({"version": "1.1.6", "data": {"alpha-1:2": {"survival_rounds": 7}}}),
        encoding="utf-8",
    )
    (root / "memory" / "evolution" / "pending_rewards.json").write_text(
        json.dumps({"version": "1.1.6", "data": {}}),
        encoding="utf-8",
    )
    (root / "memory" / "evolution" / "template_stats.json").write_text(
        json.dumps({"version": "1.1.6", "data": {}}),
        encoding="utf-8",
    )
    (root / "memory" / "statistics" / "operator_statistics.json").write_text("{}", encoding="utf-8")
    (root / "memory" / "failure_patterns" / "failures.json").write_text(
        json.dumps([{"error_type": "operator misuse", "expression": "vec_avg(close)", "root_cause": "Invalid number of inputs"}]),
        encoding="utf-8",
    )
    (root / "iteration_log.csv").write_text(
        "time,alpha_name,iteration,stage,code,platform_error,quality_json,metrics_json,behavior_family,estimated_self_corr\n",
        encoding="utf-8",
    )


def _insight(
    summary: str,
    *,
    support: int = 5,
    contradiction: int = 0,
    confidence: float = 0.6,
    operators: list[str] | None = None,
    rounds: list[int] | None = None,
) -> ResearchInsight:
    return ResearchInsight(
        id="",
        type="regime",
        summary=summary,
        confidence=confidence,
        support_count=support,
        contradiction_count=contradiction,
        freshness_score=0.8,
        decay_score=0.8,
        source_rounds=rounds or [1, 2],
        related_operators=operators or ["rank", "ts_mean"],
        market_tags=["mean_reversion"],
        created_at="2026-05-08T10:00:00",
        updated_at="2026-05-08T10:00:00",
    )


if __name__ == "__main__":
    unittest.main()
