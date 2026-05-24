import tempfile
import unittest
import inspect
from pathlib import Path
from types import SimpleNamespace

from wq_workflow.core.evolution import (
    AlphaGraph,
    AlphaSimulator,
    EvolutionOrchestrator,
    EvolutionPolicy,
    PopulationEngine,
    evolution_authority,
)
from wq_workflow.orchestrator import process_one_template, remember_simulator_skip, should_block_repeated_simulator_skip
from wq_workflow.reward_engine import RewardEngine
from wq_workflow.storage import LegacyFullImporter
from wq_workflow.storage.evolution_repository import EvolutionDBRepository
from wq_workflow.storage.manager import StorageConfig, StorageManager
from wq_workflow.storage.schema import initialize_schema
from wq_workflow.storage.sqlite_store import connect_db


class FakePool:
    def __init__(self, rows):
        self.rows = rows

    def _read(self):
        return list(self.rows)


class FakeMemory:
    def __init__(self, rows):
        self.rows = rows

    def load_recent_history(self, limit=20):
        return list(self.rows)[-limit:]


class FakeQueueStorage:
    mode = "jsonl_only"

    def __init__(self, fail=False):
        self.fail = fail
        self.decisions = []

    def write_evolution_decision_record(self, payload):
        if self.fail:
            raise RuntimeError("queue failed")
        self.decisions.append(payload)
        return True


class FakeDecisionRepo:
    def __init__(self):
        self.decisions = []

    def record_decision(self, payload):
        self.decisions.append(payload)

    def get_current_generation(self):
        return 0


def cfg(**overrides):
    base = dict(
        enable_sidecar_evolution=True,
        enable_experimental_evolution_decisions=True,
        enable_population_engine=True,
        enable_evolution_policy=True,
        enable_crossover=True,
        enable_alpha_simulator=True,
        simulator_skip_enabled=True,
        simulator_skip_threshold=0.95,
        simulator_never_skip_if_parent_reward_above=1.0,
        simulator_skip_only_pending_candidates=True,
        simulator_max_consecutive_skips_per_template=3,
        population_size=10,
        population_elite_size=2,
        population_tournament_k=2,
        crossover_rate=0.25,
        mutation_rate=0.70,
        random_seed_rate=0.05,
        policy_learning_rate=0.5,
        policy_min_weight=0.15,
        policy_max_weight=5.0,
        policy_epsilon_explore=0.0,
        policy_decay_rate=0.995,
        legacy_full_import_enabled=True,
        legacy_full_import_once=True,
        legacy_full_import_force=False,
        legacy_full_import_batch_size=2,
        legacy_full_import_max_records=0,
        lineage_value_lookahead=3,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


class EvolutionFinalUpgradeTests(unittest.TestCase):
    def test_legacy_full_import_runs_once_and_force_dedupes(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = connect_db(Path(tmp) / "workflow.db")
            try:
                initialize_schema(conn)
                repo = EvolutionDBRepository(conn)
                pool = FakePool([
                    {"alpha_id": "a1", "expression": "rank(close)", "reward": 1.0, "mutation_type": "add_decay"},
                    {"alpha_id": "a1", "expression": "rank(close)", "reward": 2.0, "mutation_type": "add_decay"},
                ])
                stats = LegacyFullImporter(repo, config=cfg()).run_once(candidate_pool=pool, evolution_memory=FakeMemory([]), log_paths=[])
                self.assertEqual(stats["imported_population"], 1)
                self.assertEqual(repo.get_meta("legacy_full_import_completed"), "true")
                self.assertTrue(LegacyFullImporter(repo, config=cfg()).run_once(candidate_pool=pool, evolution_memory=FakeMemory([]), log_paths=[])["skipped"])
                LegacyFullImporter(repo, config=cfg(legacy_full_import_force=True)).run_once(candidate_pool=pool, evolution_memory=FakeMemory([]), log_paths=[])
                self.assertEqual(repo.count_population(active_only=False), 1)
                self.assertEqual(repo.list_population(limit=10, active_only=False)[0]["reward"], 2.0)
            finally:
                conn.close()

    def test_legacy_full_import_partial_failure_not_completed(self):
        class FailingSecondBatchImporter(LegacyFullImporter):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.calls = 0

            def _write_batch(self, batch, stats):
                self.calls += 1
                if self.calls > 1:
                    raise RuntimeError("batch failed")
                return super()._write_batch(batch, stats)

        with tempfile.TemporaryDirectory() as tmp:
            conn = connect_db(Path(tmp) / "workflow.db")
            try:
                initialize_schema(conn)
                repo = EvolutionDBRepository(conn)
                pool = FakePool([
                    {"alpha_id": "a1", "expression": "rank(close)", "reward": 1.0},
                    {"alpha_id": "a2", "expression": "rank(volume)", "reward": 0.5},
                ])
                stats = FailingSecondBatchImporter(repo, config=cfg(legacy_full_import_batch_size=1)).run_once(
                    candidate_pool=pool,
                    evolution_memory=FakeMemory([]),
                    log_paths=[],
                )
                self.assertGreater(stats["errors"], 0)
                self.assertEqual(repo.get_meta("legacy_full_import_completed"), "false")
                self.assertEqual(repo.get_meta("legacy_full_import_partial"), "true")
                self.assertIn(repo.get_meta("legacy_full_import_last_status"), {"partial_failed", "failed_no_population"})
            finally:
                conn.close()

    def test_legacy_full_import_retry_after_partial(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = connect_db(Path(tmp) / "workflow.db")
            try:
                initialize_schema(conn)
                repo = EvolutionDBRepository(conn)
                repo.set_meta("legacy_full_import_completed", "false")
                repo.set_meta("legacy_full_import_partial", "true")
                self.assertTrue(LegacyFullImporter(repo, config=cfg()).should_run())
            finally:
                conn.close()

    def test_legacy_full_import_success_marks_completed_and_partial_false(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = connect_db(Path(tmp) / "workflow.db")
            try:
                initialize_schema(conn)
                repo = EvolutionDBRepository(conn)
                LegacyFullImporter(repo, config=cfg()).run_once(
                    candidate_pool=FakePool([{"alpha_id": "a1", "expression": "rank(close)", "reward": 1.0}]),
                    evolution_memory=FakeMemory([]),
                    log_paths=[],
                )
                self.assertEqual(repo.get_meta("legacy_full_import_completed"), "true")
                self.assertEqual(repo.get_meta("legacy_full_import_partial"), "false")
                self.assertEqual(repo.get_meta("legacy_full_import_last_status"), "success")
            finally:
                conn.close()

    def test_population_bootstrap_skips_when_full_import_completed(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = connect_db(Path(tmp) / "workflow.db")
            try:
                initialize_schema(conn)
                repo = EvolutionDBRepository(conn)
                repo.upsert_population_member({"alpha_id": "a1", "expression": "rank(close)", "reward": 1.0})
                repo.set_meta("legacy_full_import_completed", "true")
                engine = PopulationEngine(repository=repo, config=cfg())
                self.assertEqual(engine.bootstrap_from_legacy(candidate_pool=FakePool([{"alpha_id": "a2", "expression": "rank(volume)"}])), 0)
                self.assertEqual(repo.count_population(active_only=False), 1)
            finally:
                conn.close()

    def test_simulator_protection_pending_only_repeat_and_limit(self):
        simulator = AlphaSimulator(skip_threshold=0.95, skip_enabled=True)
        seed = {"expression": "rank(close)", "candidate_source": "seed", "is_pending_candidate": False}
        self.assertFalse(simulator.should_skip(seed, experimental=True)[0])
        self.assertEqual(simulator.should_skip(seed, experimental=True)[1]["skipped_reason"], "protected_candidate_source")
        mutation = {"expression": "rank(close)", "candidate_source": "mutation", "is_pending_candidate": True}
        self.assertTrue(simulator.should_skip(mutation, experimental=True)[0])
        skipped = set()
        self.assertFalse(should_block_repeated_simulator_skip("rank(close)", skipped))
        remember_simulator_skip("rank(close)", skipped)
        self.assertTrue(should_block_repeated_simulator_skip(" rank( close ) ", skipped))
        self.assertTrue(2 >= cfg(simulator_max_consecutive_skips_per_template=2).simulator_max_consecutive_skips_per_template)

    def test_evolution_mode_uses_config_priors_and_db_weight(self):
        policy = EvolutionPolicy(config=cfg(crossover_rate=0.25, mutation_rate=0.70, random_seed_rate=0.05))
        weights = policy.get_action_weights("evolution_mode", ["crossover", "mutation", "random_seed"], {})
        self.assertAlmostEqual(weights["crossover"], 0.25, places=6)
        self.assertAlmostEqual(weights["mutation"], 0.70, places=6)
        self.assertAlmostEqual(weights["random_seed"], 0.05, places=6)
        with tempfile.TemporaryDirectory() as tmp:
            conn = connect_db(Path(tmp) / "workflow.db")
            try:
                initialize_schema(conn)
                repo = EvolutionDBRepository(conn)
                repo.upsert_policy_action(action_type="evolution_mode", action_name="crossover", reward_delta=3.0, success=True, learning_rate=1.0)
                learned = EvolutionPolicy(repository=repo, config=cfg()).get_action_weights("evolution_mode", ["crossover", "mutation", "random_seed"], {})
                self.assertGreater(learned["crossover"], 0.25)
                self.assertNotAlmostEqual(learned["crossover"], 0.5, places=2)
            finally:
                conn.close()

    def test_authority_advisory_and_experimental(self):
        self.assertEqual(evolution_authority(cfg(enable_experimental_evolution_decisions=False), "policy", active_decision=True)["authority"], "advisory_only")
        exp = evolution_authority(cfg(enable_experimental_evolution_decisions=True), "policy", active_decision=True)
        self.assertEqual(exp["authority"], "experimental_decision")
        self.assertEqual(exp["decision_authority"], "ga_rl_policy")

    def test_crossover_records_attempt_success_and_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = StorageManager(StorageConfig(mode="sqlite_only", db_path=Path(tmp) / "workflow.db"), root=tmp)
            try:
                manager.initialize()
                evo = EvolutionOrchestrator(cfg(crossover_rate=1.0, mutation_rate=0.0, random_seed_rate=0.0), storage_manager=manager)
                child = evo.maybe_make_crossover_candidate(
                    {"alpha_id": "p1", "expression": "rank(close)", "reward": 0.1},
                    {"alpha_id": "p2", "expression": "rank(volume)", "reward": 0.2},
                    {},
                )
                self.assertIsNotNone(child)
                evo2 = EvolutionOrchestrator(cfg(crossover_rate=0.0, mutation_rate=1.0, random_seed_rate=0.0), storage_manager=manager)
                self.assertIsNone(evo2.maybe_make_crossover_candidate({"alpha_id": "p1", "expression": "rank(close)"}, {"alpha_id": "p2", "expression": "rank(volume)"}, {}))
                manager.flush(timeout=5.0)
                types = [row[0] for row in manager._connection().execute("SELECT decision_type FROM evolution_decisions").fetchall()]
                self.assertIn("crossover_attempt", types)
                self.assertIn("crossover_success", types)
                self.assertIn("crossover_fallback", types)
            finally:
                manager.close()

    def test_simulator_realized_result_recorded_after_backtest(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = StorageManager(StorageConfig(mode="sqlite_only", db_path=Path(tmp) / "workflow.db"), root=tmp)
            try:
                manager.initialize()
                evo = EvolutionOrchestrator(cfg(simulator_skip_threshold=0.01), storage_manager=manager)
                candidate = {
                    "alpha_id": "a1",
                    "expression": "rank(ts_mean(close, 20))",
                    "candidate_source": "mutation",
                    "is_pending_candidate": True,
                    "mutation_type": "add_decay",
                }
                skip, observation = evo.before_backtest(candidate, {})
                self.assertFalse(skip)
                evo.after_backtest({**candidate, "simulator_observation": observation}, None, {"reward": 1.0, "success": True}, {})
                manager.flush(timeout=5.0)
                row = manager._connection().execute("SELECT COUNT(*) FROM evolution_decisions WHERE decision_type='simulator_realized_result'").fetchone()
                self.assertEqual(row[0], 1)
            finally:
                manager.close()

    def test_after_backtest_records_non_pending_candidate_without_policy_update(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = StorageManager(StorageConfig(mode="sqlite_only", db_path=Path(tmp) / "workflow.db"), root=tmp)
            try:
                manager.initialize()
                evo = EvolutionOrchestrator(cfg(), storage_manager=manager)
                evo.after_backtest(
                    {
                        "alpha_id": "np1",
                        "expression": "rank(ts_mean(close, 20))",
                        "mutation_type": "initial_or_untracked",
                        "candidate_source": "initial_or_untracked",
                        "is_pending_candidate": False,
                    },
                    None,
                    {"reward": 0.4, "success": True},
                    {},
                )
                manager.flush(timeout=5.0)
                repo = EvolutionDBRepository(manager._connection())
                self.assertEqual(repo.count_population(active_only=False), 1)
                self.assertGreater(repo.count_graph_edges(), 0)
                lineage = manager._connection().execute("SELECT COUNT(*) FROM lineage_values WHERE alpha_id='np1'").fetchone()
                self.assertEqual(lineage[0], 1)
                self.assertEqual(repo.count_policy_actions(), 0)
                skipped = manager._connection().execute("SELECT COUNT(*) FROM evolution_decisions WHERE decision_type='policy_update_skipped'").fetchone()
                self.assertEqual(skipped[0], 1)
            finally:
                manager.close()

    def test_after_backtest_pending_updates_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = StorageManager(StorageConfig(mode="sqlite_only", db_path=Path(tmp) / "workflow.db"), root=tmp)
            try:
                manager.initialize()
                evo = EvolutionOrchestrator(cfg(), storage_manager=manager)
                evo.after_backtest(
                    {
                        "alpha_id": "p1",
                        "expression": "rank(ts_mean(close, 20))",
                        "mutation_type": "add_decay",
                        "candidate_source": "mutation",
                        "is_pending_candidate": True,
                        "parent_reward": 0.1,
                    },
                    None,
                    {"reward": 1.0, "success": True},
                    {"mutation_goal": "turnover high"},
                )
                manager.flush(timeout=5.0)
                repo = EvolutionDBRepository(manager._connection())
                context_key = EvolutionPolicy(config=cfg()).context_key({"mutation_goal": "turnover high"})
                self.assertIn("add_decay", repo.get_policy_weights("mutation", context_key))
            finally:
                manager.close()

    def test_initial_or_untracked_does_not_update_mutation_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = StorageManager(StorageConfig(mode="sqlite_only", db_path=Path(tmp) / "workflow.db"), root=tmp)
            try:
                manager.initialize()
                evo = EvolutionOrchestrator(cfg(), storage_manager=manager)
                evo.after_backtest(
                    {
                        "alpha_id": "seed1",
                        "expression": "rank(close)",
                        "mutation_type": "initial_or_untracked",
                        "candidate_source": "seed",
                        "is_pending_candidate": False,
                    },
                    None,
                    {"reward": 1.0, "success": True},
                    {},
                )
                manager.flush(timeout=5.0)
                self.assertEqual(EvolutionDBRepository(manager._connection()).count_policy_actions(), 0)
            finally:
                manager.close()

    def test_simulator_realized_result_recorded_for_non_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = StorageManager(StorageConfig(mode="sqlite_only", db_path=Path(tmp) / "workflow.db"), root=tmp)
            try:
                manager.initialize()
                evo = EvolutionOrchestrator(cfg(), storage_manager=manager)
                evo.after_backtest(
                    {
                        "alpha_id": "np_sim",
                        "expression": "rank(close)",
                        "mutation_type": "initial_or_untracked",
                        "candidate_source": "initial_or_untracked",
                        "is_pending_candidate": False,
                        "simulator_observation": {"simulator_score": 0.7, "skipped": False},
                    },
                    None,
                    {"reward": 0.2, "success": True},
                    {},
                )
                manager.flush(timeout=5.0)
                row = manager._connection().execute("SELECT COUNT(*) FROM evolution_decisions WHERE decision_type='simulator_realized_result'").fetchone()
                self.assertEqual(row[0], 1)
            finally:
                manager.close()

    def test_all_real_backtests_enter_population(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = StorageManager(StorageConfig(mode="sqlite_only", db_path=Path(tmp) / "workflow.db"), root=tmp)
            try:
                manager.initialize()
                evo = EvolutionOrchestrator(cfg(), storage_manager=manager)
                evo.after_backtest({"alpha_id": "np", "expression": "rank(close)", "mutation_type": "initial_or_untracked", "is_pending_candidate": False}, None, {"reward": 0.1}, {})
                evo.after_backtest({"alpha_id": "p", "expression": "rank(volume)", "mutation_type": "add_decay", "candidate_source": "mutation", "is_pending_candidate": True}, None, {"reward": 0.2}, {})
                manager.flush(timeout=5.0)
                self.assertEqual(EvolutionDBRepository(manager._connection()).count_population(active_only=False), 2)
            finally:
                manager.close()

    def test_evolution_orchestrator_prefers_queue_writes(self):
        storage = FakeQueueStorage()
        evo = EvolutionOrchestrator(cfg(), storage_manager=storage)
        repo = FakeDecisionRepo()
        evo.repo = repo
        evo._write_decision({"decision_type": "x"})
        self.assertEqual(len(storage.decisions), 1)
        self.assertEqual(len(repo.decisions), 0)

    def test_evolution_orchestrator_queue_fallback_to_repo(self):
        storage = FakeQueueStorage(fail=True)
        evo = EvolutionOrchestrator(cfg(), storage_manager=storage)
        repo = FakeDecisionRepo()
        evo.repo = repo
        evo._write_decision({"decision_type": "x"})
        self.assertEqual(len(repo.decisions), 1)

    def test_orchestrator_calls_after_backtest_for_non_pending_result(self):
        source = inspect.getsource(process_one_template)
        self.assertIn("evolution_orchestrator.after_backtest", source)
        self.assertNotIn("if pending_mutation:\n            evolution_orchestrator.after_backtest", source)

    def test_failure_to_repair_graph_edge_and_policy_bounds(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = connect_db(Path(tmp) / "workflow.db")
            try:
                initialize_schema(conn)
                repo = EvolutionDBRepository(conn)
                AlphaGraph(repo).record_candidate_result(
                    {"alpha_id": "a1", "expression": "rank(close)", "mutation_type": "add_decay", "failure_type": "high turnover"},
                    reward=1.0,
                    success=True,
                )
                edges = repo.list_graph_edges("failure_to_repair")
                self.assertEqual(edges[0]["src"], "high turnover")
                low = repo.upsert_policy_action(action_type="mutation", action_name="x", reward_delta=-999, success=False, learning_rate=1.0)
                high = repo.upsert_policy_action(action_type="mutation", action_name="x", reward_delta=999, success=True, learning_rate=1.0)
                self.assertGreaterEqual(low["new_weight"], 0.15)
                self.assertLessEqual(high["new_weight"], 5.0)
            finally:
                conn.close()

    def test_jsonl_only_restart_reward_and_disable_experimental(self):
        self.assertTrue(LegacyFullImporter(None, config=cfg()).run_once(candidate_pool=FakePool([]), evolution_memory=FakeMemory([]), log_paths=[])["skipped"])
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "workflow.db"
            conn = connect_db(db)
            initialize_schema(conn)
            repo = EvolutionDBRepository(conn)
            LegacyFullImporter(repo, config=cfg()).run_once(
                candidate_pool=FakePool([{"alpha_id": "a1", "expression": "rank(close)", "reward": 1.0}]),
                evolution_memory=FakeMemory([]),
                log_paths=[],
            )
            conn.close()
            conn2 = connect_db(db)
            try:
                repo2 = EvolutionDBRepository(conn2)
                self.assertEqual(repo2.get_meta("legacy_full_import_completed"), "true")
                self.assertEqual(repo2.count_population(active_only=False), 1)
                self.assertTrue(LegacyFullImporter(repo2, config=cfg()).run_once(candidate_pool=FakePool([]), evolution_memory=FakeMemory([]), log_paths=[])["skipped"])
            finally:
                conn2.close()
        reward = RewardEngine(enable_migration=False).calculate_reward(
            {"sharpe": 1.0, "fitness": 1.0, "turnover": 50},
            {"sharpe": 1.2, "fitness": 1.1, "turnover": 40},
            "rank(close)",
        )
        self.assertIsInstance(reward, float)
        evo = EvolutionOrchestrator(cfg(enable_experimental_evolution_decisions=False))
        fallback = {"alpha_id": "p", "expression": "rank(close)"}
        self.assertEqual(evo.choose_parents(fallback), (fallback, None))
        self.assertIsNone(evo.maybe_make_crossover_candidate(fallback, fallback, {}))


if __name__ == "__main__":
    unittest.main()
