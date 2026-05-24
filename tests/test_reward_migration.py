import tempfile
import unittest
from pathlib import Path

from wq_workflow.reward_engine import RewardBreakdown, RewardEngine
from wq_workflow.reward_migration import MigrationController
from wq_workflow.reward_migration.migration_state import MigrationState
from wq_workflow.reward_migration.population_health import PopulationHealthMonitor
from wq_workflow.reward_migration.reward_stability_monitor import RewardStabilityMonitor


def _controller(root: Path) -> MigrationController:
    return MigrationController(
        state_path=root / "migration_state.json",
        metrics_path=root / "migration_metrics.json",
        shadow_log_dir=root / "reward_shadow_logs",
        migration_log_dir=root / "migration_logs",
        health_monitor=PopulationHealthMonitor(
            pool_path=root / "candidate_pool.json",
            lineage_path=root / "alpha_lineage.json",
            min_sample_size=4,
        ),
        stability_monitor=RewardStabilityMonitor(min_sample_size=4),
        min_hybrid_samples=4,
        healthy_streak_to_advance=2,
        full_takeover_streak=4,
    )


class RewardMigrationTests(unittest.TestCase):
    def test_reward_engine_keeps_legacy_output_in_shadow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            controller = _controller(Path(tmp))
            reward = RewardEngine(migration_controller=controller).calculate_reward(
                {"sharpe": 1.0, "fitness": 0.5, "turnover": 0.60},
                {"sharpe": 1.2, "fitness": 0.7, "turnover": 50.0},
                "rank(ts_mean(close, 20))",
                alpha_id="a1",
                v2_reward=2.0,
            )

            self.assertAlmostEqual(reward, 0.18, places=6)
            self.assertEqual(controller.store.load().state, MigrationState.SHADOW)
            self.assertTrue((Path(tmp) / "reward_shadow_logs" / "reward_shadow.jsonl").exists())

    def test_hybrid_reward_blends_legacy_and_v2(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            controller = _controller(root)
            snapshot = controller.store.load()
            snapshot.state = MigrationState.EARLY_HYBRID
            snapshot.legacy_weight = 0.9
            snapshot.v2_weight = 0.1
            controller.store.save(snapshot)

            decision = controller.blend_reward(
                alpha_id="a2",
                legacy_reward=1.0,
                v2_breakdown=RewardBreakdown(legacy_reward=1.0, final_reward=3.0),
            )

            self.assertEqual(decision.state, MigrationState.EARLY_HYBRID)
            self.assertAlmostEqual(decision.final_reward, 2.0, places=6)
            self.assertAlmostEqual(decision.v2_weight, 0.5, places=6)

    def test_rollback_triggers_on_diversity_collapse(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            controller = _controller(root)
            snapshot = controller.store.load()
            snapshot.state = MigrationState.MID_HYBRID
            snapshot.legacy_weight = 0.5
            snapshot.v2_weight = 0.5
            controller.store.save(snapshot)
            pool_rows = [
                {"alpha_id": f"a{i}", "diversity_score": 0.1, "max_semantic_similarity": 0.95, "reward": 1.0}
                for i in range(6)
            ]

            decision = controller.blend_reward(
                alpha_id="a3",
                legacy_reward=1.0,
                v2_breakdown={"final_reward": 4.0},
                context={"pool_rows": pool_rows},
            )

            self.assertEqual(decision.state, MigrationState.ROLLBACK)
            self.assertEqual(decision.v2_weight, 0.0)
            self.assertEqual(decision.final_reward, 1.0)
            self.assertIn("diversity_collapse", decision.health.risk_flags)

    def test_rollback_hold_does_not_increment_count_repeatedly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            controller = _controller(root)
            snapshot = controller.store.load()
            snapshot.state = MigrationState.MID_HYBRID
            snapshot.legacy_weight = 0.5
            snapshot.v2_weight = 0.5
            controller.store.save(snapshot)
            pool_rows = [
                {"alpha_id": f"a{i}", "diversity_score": 0.1, "max_semantic_similarity": 0.95, "reward": 1.0}
                for i in range(6)
            ]

            first = controller.blend_reward(
                alpha_id="a3",
                legacy_reward=1.0,
                v2_breakdown={"final_reward": 4.0},
                context={"pool_rows": pool_rows},
            )
            second = controller.blend_reward(
                alpha_id="a4",
                legacy_reward=1.0,
                v2_breakdown={"final_reward": 4.0},
                context={"pool_rows": pool_rows},
            )

            self.assertEqual(first.action, "rollback")
            self.assertEqual(second.action, "rollback_hold")
            self.assertEqual(controller.store.load().rollback_count, 1)

    def test_controller_never_allows_full_takeover_after_stable_health(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            controller = _controller(Path(tmp))
            snapshot = controller.store.load()
            snapshot.state = MigrationState.LATE_HYBRID
            snapshot.healthy_streak = 8
            health = controller.health_monitor.evaluate(
                pool_rows=[
                    {"alpha_id": f"a{i}", "diversity_score": 0.7, "max_semantic_similarity": 0.2, "reward": 1.0, "passed": True}
                    for i in range(8)
                ],
                lineage_rows=[
                    {"alpha_id": f"c{i}", "parent_id": f"p{i % 4}", "reward": 1.0, "passed": True}
                    for i in range(8)
                ],
            )
            stability = controller.stability_monitor.evaluate(
                [
                    {"legacy_reward": 1.0 + i * 0.01, "v2_reward": 1.1 + i * 0.01, "ranking_delta": 0.02}
                    for i in range(12)
                ]
            )

            self.assertFalse(controller.can_full_takeover(health, stability, snapshot))

    def test_late_hybrid_never_transitions_to_full_v2(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            controller = _controller(root)
            snapshot = controller.store.load()
            snapshot.state = MigrationState.LATE_HYBRID
            snapshot.healthy_streak = 20
            snapshot.legacy_weight = 0.15
            snapshot.v2_weight = 0.85
            controller.store.save(snapshot)
            pool_rows = [
                {"alpha_id": f"a{i}", "diversity_score": 0.7, "max_semantic_similarity": 0.2, "reward": 1.0, "passed": True}
                for i in range(8)
            ]
            lineage_rows = [
                {"alpha_id": f"c{i}", "parent_id": f"p{i % 4}", "reward": 1.0, "passed": True}
                for i in range(8)
            ]

            decision = controller.blend_reward(
                alpha_id="stable",
                legacy_reward=1.0,
                v2_breakdown={"final_reward": 4.0},
                context={"pool_rows": pool_rows, "lineage_rows": lineage_rows},
            )

            self.assertEqual(decision.state, MigrationState.LATE_HYBRID)
            self.assertGreaterEqual(decision.legacy_weight, 0.15)
            self.assertLessEqual(decision.v2_weight, 0.85)


if __name__ == "__main__":
    unittest.main()
