import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

from wq_workflow.storage.repository import EventRepository
from wq_workflow.storage.evolution_repository import EvolutionDBRepository
from wq_workflow.storage.manager import StorageConfig, StorageManager
from wq_workflow.storage.schema import initialize_schema
from wq_workflow.storage.sqlite_store import connect_db
from wq_workflow.storage.write_queue import SQLiteWriteQueue


class StorageWriteQueueTests(unittest.TestCase):
    def test_queue_batches_sqlite_and_legacy_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = root / "runtime" / "db" / "workflow.db"
            log_path = root / "logs" / "workflow_state.jsonl"
            queue = SQLiteWriteQueue(db, root=root, batch_size=25, flush_interval_seconds=0.05)
            try:
                def writer(offset: int) -> None:
                    for index in range(20):
                        queue.put_event(
                            log_path,
                            {
                                "time": "2026-05-08T10:00:00",
                                "event": "STATE_PROGRESS",
                                "alpha_id": f"a{offset + index}",
                                "state": "WAIT_RESULT",
                            },
                            legacy_export=True,
                            max_bytes=1024 * 1024,
                        )

                threads = [threading.Thread(target=writer, args=(i * 20,)) for i in range(3)]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join()
                self.assertTrue(queue.flush(timeout=5.0))
            finally:
                queue.close()

            conn = connect_db(db)
            try:
                initialize_schema(conn)
                events = EventRepository(conn, root=root).tail_for_path(log_path, limit=100)
                self.assertEqual(len(events), 60)
            finally:
                conn.close()
            self.assertEqual(len(log_path.read_text(encoding="utf-8").splitlines()), 60)

    def test_queue_failure_triggers_degraded_callback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bad_db = root / "runtime" / "db"
            bad_db.mkdir(parents=True)
            degraded: list[str] = []

            queue = SQLiteWriteQueue(
                bad_db,
                root=root,
                degraded_callback=lambda enabled, reason: degraded.append(reason) if enabled else None,
            )
            time.sleep(0.2)
            queue.close()

            self.assertTrue(degraded)

    def test_sqlite_queue_evolution_kinds(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = root / "runtime" / "db" / "workflow.db"
            queue = SQLiteWriteQueue(db, root=root, batch_size=10, flush_interval_seconds=0.05)
            try:
                queue.put_evolution_population({"alpha_id": "e1", "expression": "rank(close)", "survival_score": 0.6})
                queue.put_evolution_policy({"action_type": "mutation", "action_name": "add_decay", "reward_delta": 0.4, "success": True})
                queue.put_evolution_decision({"decision_type": "mutation_selection", "action_type": "mutation", "action_name": "add_decay"})
                queue.put_evolution_graph({"edge_type": "operator_pair", "src": "rank", "dst": "ts_mean", "reward": 0.4, "success": True})
                queue.put_lineage_value({"alpha_id": "e1", "long_term_value": 0.3})
                queue.put_simulator_observation({"alpha_id": "e1", "expression": "rank(close)", "simulator_score": 0.5})
                self.assertTrue(queue.flush(timeout=5.0))
            finally:
                queue.close()

            conn = connect_db(db)
            try:
                initialize_schema(conn)
                repo = EvolutionDBRepository(conn)
                self.assertEqual(repo.list_population()[0]["alpha_id"], "e1")
                self.assertIn("add_decay", repo.get_policy_weights("mutation"))
                self.assertEqual(repo.list_graph_edges("operator_pair")[0]["dst"], "ts_mean")
            finally:
                conn.close()

    def test_jsonl_only_mode_evolution_writes_no_crash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manager = StorageManager(StorageConfig(mode="jsonl_only", db_path=root / "workflow.db"), root=root)
            try:
                manager.write_evolution_population_record({"alpha_id": "e1", "expression": "rank(close)"})
                manager.write_evolution_decision_record({"decision_type": "noop"})
                manager.write_evolution_policy_record({"action_type": "mutation", "action_name": "add_decay"})
                manager.write_evolution_graph_record({"edge_type": "operator_pair", "src": "rank", "dst": "close"})
                manager.write_simulator_observation_record({"alpha_id": "e1"})
            finally:
                manager.close()
            self.assertFalse((root / "workflow.db").exists())


if __name__ == "__main__":
    unittest.main()
