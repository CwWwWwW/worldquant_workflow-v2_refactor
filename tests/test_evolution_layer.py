import tempfile
import unittest
import json
from pathlib import Path

from wq_workflow.core.evolution import (
    AdaptiveLegacyController,
    PendingRewardManager,
    SurvivalMemoryManager,
    TemplatePopulationController,
)
from wq_workflow.reward_engine import RewardEngine
from wq_workflow.reward_migration import MigrationController
from wq_workflow.reward_migration.population_health import PopulationHealthMonitor
from wq_workflow.reward_migration.reward_stability_monitor import RewardStabilityMonitor
from wq_workflow.reward_migration.migration_state import MigrationSnapshot, MigrationState
from wq_workflow.v2_engine import AdaptiveMutationScheduler, build_behavior_fingerprint


class EvolutionLayerTests(unittest.TestCase):
    def test_survival_score_formula(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = SurvivalMemoryManager(Path(tmp) / "survival.json", Path(tmp) / "survival.log")
            manager.register_alpha("a1", generation_created=12, template="family", operator="swap", parent="p1", lineage_depth=3)
            for _ in range(7):
                manager.update_survival("a1", passed=True)
            for _ in range(2):
                manager.update_survival("a1", passed=False)
            for _ in range(4):
                manager.increment_children_success("a1")
            record = manager.update_decay("a1", 0.18)

            self.assertAlmostEqual(record["long_term_score"], 1.946, places=6)
            self.assertEqual(record["behavior_family"], "family")

    def test_versioned_memory_loads_raw_and_recovers_backup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "survival.json"
            path.write_text(json.dumps({"a1": {"template": "legacy_family", "lineage_depth": 1}}), encoding="utf-8")
            manager = SurvivalMemoryManager(path, Path(tmp) / "survival.log")

            self.assertEqual(manager.load_memory()["a1"]["behavior_family"], "legacy_family")

            path.write_text("{broken", encoding="utf-8")
            path.with_suffix(path.suffix + ".bak").write_text(
                json.dumps({"version": "1.1.6", "data": {"a2": {"behavior_family": "backup_family"}}}),
                encoding="utf-8",
            )

            self.assertEqual(manager.load_memory()["a2"]["behavior_family"], "backup_family")

    def test_survival_memory_writes_wrapped_payload_and_flushes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "survival.json"
            manager = SurvivalMemoryManager(path, Path(tmp) / "survival.log")
            manager.register_alpha("a1", behavior_family="family")
            manager.flush()
            payload = json.loads(path.read_text(encoding="utf-8"))

            self.assertEqual(payload["version"], "1.1.6")
            self.assertIn("a1", payload["data"])
            self.assertTrue(path.with_suffix(path.suffix + ".bak").exists())

    def test_pending_reward_release_cancel_and_direction_adjustment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            survival = SurvivalMemoryManager(root / "survival.json", root / "survival.log")
            pending = PendingRewardManager(root / "pending.json", root / "pending.log", settle_after=5, injection_weight=0.15)
            survival.register_alpha("released", generation_created=1, template="family", operator="swap")
            for _ in range(5):
                survival.update_survival("released", passed=True)
            survival.register_alpha("canceled", generation_created=1, template="other", operator="swap")
            pending.register_pending_reward("released", 2.0, created_generation=1, template="family", operator="swap")
            pending.register_pending_reward("canceled", 2.0, created_generation=1, template="other", operator="swap")

            settlement = pending.settle_rewards(
                current_generation=6,
                survival_manager=survival,
                current_behavior_family="family",
                current_operator="swap",
                current_lineage="",
            )

            self.assertEqual(settlement["released_count"], 1)
            self.assertEqual(settlement["canceled_count"], 1)
            self.assertGreater(settlement["injection"]["family_weight"], 0)
            self.assertGreater(settlement["injection"]["operator_credibility"], 0)
            self.assertEqual(survival.load_memory()["released"]["long_term_score"], 0.75)
            pending.flush()
            payload = json.loads((root / "pending.json").read_text(encoding="utf-8"))
            self.assertIn("injections", payload)
            self.assertTrue(payload["data"]["released"]["released"])

    def test_template_population_soft_penalty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            controller = TemplatePopulationController(Path(tmp) / "templates.json", Path(tmp) / "templates.log")
            rows = [
                {"alpha_id": f"a{i}", "behavior_family": "dominant", "reward": 1.0, "estimated_self_corr": 0.8}
                for i in range(4)
            ] + [
                {"alpha_id": "b1", "behavior_family": "minor", "reward": -0.1, "estimated_self_corr": 0.2}
            ]
            stats = controller.update_template_stats(rows)
            adjusted, penalty = controller.apply_penalty(1.0, "dominant")

            self.assertGreater(stats["dominant"]["population_share"], 0.35)
            self.assertAlmostEqual(adjusted, 0.7, places=6)
            self.assertEqual(penalty["penalty_multiplier"], 0.7)
            self.assertGreater(penalty["exploration_pressure"], 0.0)
            self.assertGreater(controller.increase_cross_family_mutation("dominant"), 0.0)

    def test_scheduler_softly_injects_exploration_pressure(self) -> None:
        base = AdaptiveMutationScheduler().schedule(
            {"fitness": 1.2, "turnover": 20},
            build_behavior_fingerprint("rank(close)"),
            {"estimated_self_corr": 0.2},
        )
        pressured = AdaptiveMutationScheduler().schedule(
            {"fitness": 1.2, "turnover": 20},
            build_behavior_fingerprint("rank(close)"),
            {"estimated_self_corr": 0.2},
            exploration_pressure=0.8,
        )

        self.assertLess(pressured.similarity_limit, base.similarity_limit)
        self.assertGreater(pressured.weights["operator_replace"], base.weights["operator_replace"])

    def test_adaptive_legacy_weight_clamps(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            controller = AdaptiveLegacyController(Path(tmp) / "adaptive.log")
            low = controller.compute_legacy_weight(
                reward_future_corr=10,
                lineage_entropy=10,
                template_diversity=10,
            )
            high = controller.compute_legacy_weight(rollback_count=20, reward_variance=50)

            self.assertEqual(low, 0.15)
            self.assertEqual(high, 0.85)

    def test_full_v2_input_normalizes_to_hybrid_floor(self) -> None:
        snapshot = MigrationSnapshot.from_dict({"state": "full_v2", "legacy_weight": 0.0, "v2_weight": 1.0})

        self.assertEqual(snapshot.state, MigrationState.LATE_HYBRID)
        self.assertGreaterEqual(snapshot.legacy_weight, 0.15)

    def test_reward_layer_can_be_bypassed(self) -> None:
        reward = RewardEngine(
            enable_migration=False,
            enable_survival_memory=False,
            enable_pending_reward=False,
            enable_template_governance=False,
        ).calculate_reward(
            {"sharpe": 1.0, "fitness": 0.5, "turnover": 0.60},
            {"sharpe": 1.2, "fitness": 0.7, "turnover": 50.0},
            "rank(ts_mean(close, 20))",
            alpha_id="a1",
        )

        self.assertAlmostEqual(reward, 0.18, places=6)

    def test_reward_layer_applies_long_term_and_pending_immediate_split(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            survival = SurvivalMemoryManager(root / "survival.json", root / "survival.log")
            pending = PendingRewardManager(root / "pending.json", root / "pending.log")
            template = TemplatePopulationController(root / "templates.json", root / "templates.log")
            survival.register_alpha("a1", lineage_depth=2)
            for _ in range(5):
                survival.update_survival("a1", passed=True)
            controller = MigrationController(
                state_path=root / "migration_state.json",
                metrics_path=root / "migration_metrics.json",
                shadow_log_dir=root / "reward_shadow_logs",
                migration_log_dir=root / "migration_logs",
                health_monitor=PopulationHealthMonitor(pool_path=root / "pool.json", lineage_path=root / "lineage.json"),
                stability_monitor=RewardStabilityMonitor(),
            )

            reward = RewardEngine(
                migration_controller=controller,
                survival_manager=survival,
                pending_reward_manager=pending,
                template_controller=template,
            ).calculate_reward(
                {"sharpe": 1.0, "fitness": 0.5, "turnover": 0.60},
                {"sharpe": 1.2, "fitness": 0.7, "turnover": 50.0},
                "rank(ts_mean(close, 20))",
                alpha_id="a1",
                migration_context={"generation": 1, "behavior_family": "family"},
            )

            self.assertAlmostEqual(reward, 0.18, places=6)
            shadow = (root / "reward_shadow_logs" / "reward_shadow.jsonl").read_text(encoding="utf-8")
            self.assertIn("evolution_layer", shadow)
            self.assertIn('"v2_reward": 0.309', shadow)


if __name__ == "__main__":
    unittest.main()
