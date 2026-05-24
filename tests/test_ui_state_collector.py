import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from ui.state_collector import StateCollector
from wq_workflow.storage.manager import StorageConfig, StorageManager
from wq_workflow.storage.repository import EventRepository
from wq_workflow.storage.schema import initialize_schema
from wq_workflow.storage.sqlite_store import connect_db


class StateCollectorTests(unittest.TestCase):
    def test_missing_migration_files_fallback_to_shadow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_runtime(root)
            collector = _collector(root)

            snapshot = collector.collect()

            self.assertEqual(snapshot.migration.state, "shadow")
            self.assertEqual(snapshot.migration.legacy_weight, 1.0)
            self.assertEqual(snapshot.workflow.population_count, 1)

    def test_stalled_worker_from_fsm_tail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_runtime(root)
            (root / "logs" / "workflow_active.pid").write_text(str(os.getpid()), encoding="utf-8")
            state_log = root / "logs" / "workflow_state.jsonl"
            state_log.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "time": "2026-05-08T10:00:00",
                                "event": "STATE_ENTER",
                                "alpha_id": "alpha-1",
                                "state": "WAIT_RESULT",
                            }
                        ),
                        json.dumps(
                            {
                                "time": "2026-05-08T10:24:00",
                                "event": "STATE_PROGRESS",
                                "alpha_id": "alpha-1",
                                "state": "WAIT_RESULT",
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            collector = _collector(root)

            with (
                patch("ui.state_collector._process_running", return_value=True),
                patch("ui.state_collector.time.time", return_value=_ts("2026-05-08T10:25:00")),
            ):
                snapshot = collector.collect()

            self.assertEqual(snapshot.workers[0].health, "STALLED")

    def test_workflow_not_running_clears_historical_workers_and_queue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_runtime(root)
            (root / "logs" / "workflow_state.jsonl").write_text(
                json.dumps({"time": "2026-05-08T10:00:00", "event": "STATE_ENTER", "alpha_id": "alpha-1", "state": "WAIT_QUEUE"}) + "\n",
                encoding="utf-8",
            )
            collector = _collector(root)

            snapshot = collector.collect()

            self.assertEqual(snapshot.workers, [])
            self.assertEqual(snapshot.workflow.queue_size, 0)

    def test_worker_ttl_expires_without_exit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_runtime(root)
            (root / "logs" / "workflow_active.pid").write_text(str(os.getpid()), encoding="utf-8")
            (root / "logs" / "workflow_state.jsonl").write_text(
                json.dumps({"time": "2026-05-08T10:00:00", "event": "STATE_ENTER", "alpha_id": "alpha-1", "state": "WAIT_QUEUE"}) + "\n",
                encoding="utf-8",
            )
            collector = _collector(root)

            with (
                patch("ui.state_collector._process_running", return_value=True),
                patch("ui.state_collector.time.time", return_value=_ts("2026-05-08T10:04:00")),
            ):
                snapshot = collector.collect()

            self.assertEqual(snapshot.workers, [])
            self.assertEqual(snapshot.workflow.queue_size, 0)

    def test_worker_activity_refreshes_last_seen(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_runtime(root)
            (root / "logs" / "workflow_active.pid").write_text(str(os.getpid()), encoding="utf-8")
            (root / "logs" / "workflow_state.jsonl").write_text(
                "\n".join(
                    [
                        json.dumps({"time": "2026-05-08T10:00:00", "event": "STATE_ENTER", "alpha_id": "alpha-1", "state": "WAIT_QUEUE"}),
                        json.dumps({"time": "2026-05-08T10:03:30", "event": "STATE_HEARTBEAT", "alpha_id": "alpha-1", "state": "WAIT_QUEUE"}),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            collector = _collector(root)

            with (
                patch("ui.state_collector._process_running", return_value=True),
                patch("ui.state_collector.time.time", return_value=_ts("2026-05-08T10:04:00")),
            ):
                snapshot = collector.collect()

            self.assertEqual(len(snapshot.workers), 1)
            self.assertEqual(snapshot.workflow.queue_size, 1)

    def test_stale_migration_metrics_fallback_to_shadow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_runtime(root)
            metrics = root / "memory" / "dashboard_snapshot" / "migration_metrics.snapshot.json"
            metrics.write_text(json.dumps({"current_state": "late_hybrid", "v2_weight": 0.8}), encoding="utf-8")
            collector = _collector(root)

            with patch("ui.state_collector.time.time", return_value=1_000.0):
                os.utime(metrics, (600.0, 600.0))
                snapshot = collector.collect()

            self.assertEqual(snapshot.migration.state, "shadow")
            self.assertEqual(snapshot.migration.v2_weight, 0.0)
            self.assertEqual(snapshot.workflow.reward_mode, "LEGACY")

    def test_migration_metrics_before_workflow_start_fallback_to_shadow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_runtime(root)
            pid_file = root / "logs" / "workflow_active.pid"
            pid_file.write_text(str(os.getpid()), encoding="utf-8")
            metrics = root / "memory" / "dashboard_snapshot" / "migration_metrics.snapshot.json"
            metrics.write_text(json.dumps({"current_state": "mid_hybrid", "v2_weight": 0.5}), encoding="utf-8")
            os.utime(metrics, (1_000.0, 1_000.0))
            os.utime(pid_file, (1_100.0, 1_100.0))
            collector = _collector(root)

            with (
                patch("ui.state_collector._process_running", return_value=True),
                patch("ui.state_collector.time.time", return_value=1_120.0),
            ):
                snapshot = collector.collect()

            self.assertEqual(snapshot.migration.state, "shadow")
            self.assertEqual(snapshot.migration.v2_weight, 0.0)

    def test_dirty_jsonl_rows_and_missing_fields_do_not_crash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_runtime(root)
            (root / "logs" / "workflow_active.pid").write_text(str(os.getpid()), encoding="utf-8")
            state_log = root / "logs" / "workflow_state.jsonl"
            state_log.write_bytes(
                b'{"event":"STATE_ENTER"}\n'
                b'not-json\n'
                b'["not-dict"]\n'
                b'{"time":"2026-05-08T10:00:00","event":"STATE_ENTER","alpha_id":"alpha-1","state":"WAIT_QUEUE"}\n'
                b'{"event":"STATE_ENTER","alpha_id"'
                + bytes([0xE4, 0xB8])
            )
            collector = _collector(root)

            with (
                patch("ui.state_collector._process_running", return_value=True),
                patch("ui.state_collector.time.time", return_value=_ts("2026-05-08T10:01:00")),
            ):
                snapshot = collector.collect()

            self.assertEqual(len(snapshot.workers), 2)

    def test_dashboard_uses_legacy_recovery_fields_with_optional_new_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_runtime(root)
            (root / "logs" / "workflow_active.pid").write_text(str(os.getpid()), encoding="utf-8")
            (root / "logs" / "workflow_state.jsonl").write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "time": "2026-05-08T10:00:00",
                                "event": "STATE_ENTER",
                                "alpha_id": "alpha-legacy",
                                "state": "WAIT_RESULT",
                            }
                        ),
                        json.dumps(
                            {
                                "time": "2026-05-08T10:01:00",
                                "event": "STATE_FATAL",
                                "alpha_id": "alpha-legacy",
                                "state": "BROWSER_WATCHDOG",
                                "recovery": "LEVEL_4_RESTART_BROWSER",
                                "error": "browser timeout",
                                "recovery_phase": "watchdog",
                                "circuit_breaker": "open",
                                "full_rebuild": True,
                                "browser_generation": 2,
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            collector = _collector(root)

            with (
                patch("ui.state_collector._process_running", return_value=True),
                patch("ui.state_collector.time.time", return_value=_ts("2026-05-08T10:02:00")),
            ):
                snapshot = collector.collect()

            self.assertEqual(len(snapshot.workers), 1)
            self.assertEqual(snapshot.workers[0].alpha_id, "alpha-legacy")
            self.assertEqual(snapshot.workers[0].current_task, "BROWSER_WATCHDOG")
            self.assertEqual(snapshot.workers[0].health, "FATAL")
            self.assertEqual(snapshot.workers[0].restart_count, 1)

    def test_events_older_than_max_age_are_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_runtime(root)
            (root / "logs" / "workflow_active.pid").write_text(str(os.getpid()), encoding="utf-8")
            (root / "logs" / "workflow_state.jsonl").write_text(
                json.dumps({"time": "2026-05-07T09:59:00", "event": "STATE_ENTER", "alpha_id": "alpha-old", "state": "WAIT_QUEUE"}) + "\n",
                encoding="utf-8",
            )
            collector = _collector(root)

            with (
                patch("ui.state_collector._process_running", return_value=True),
                patch("ui.state_collector.time.time", return_value=_ts("2026-05-08T10:00:00")),
            ):
                snapshot = collector.collect()

            self.assertEqual(snapshot.workers, [])

    def test_corrupt_candidate_pool_does_not_crash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_runtime(root)
            (root / "memory" / "dashboard_snapshot" / "candidate_pool.snapshot.json").write_text("{", encoding="utf-8")
            collector = _collector(root)

            snapshot = collector.collect()

            self.assertTrue(snapshot.stale)
            self.assertEqual(snapshot.population.count, 0)

    def test_dashboard_reads_snapshot_not_live_memory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_runtime(root)
            (root / "memory" / "evolution" / "candidate_pool.json").write_text("{", encoding="utf-8")
            collector = _collector(root)

            snapshot = collector.collect()

            self.assertFalse(snapshot.stale)
            self.assertEqual(snapshot.workflow.population_count, 1)

    def test_dashboard_reads_state_tail_from_sqlite_when_jsonl_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_runtime(root)
            (root / "logs" / "workflow_active.pid").write_text(str(os.getpid()), encoding="utf-8")
            db = root / "runtime" / "db" / "workflow.db"
            conn = connect_db(db)
            try:
                initialize_schema(conn)
                EventRepository(conn, root=root).insert_event(
                    root / "logs" / "workflow_state.jsonl",
                    {"time": "2026-05-08T10:00:00", "event": "STATE_ENTER", "alpha_id": "alpha-sqlite", "state": "WAIT_QUEUE"},
                )
            finally:
                conn.close()
            manager = StorageManager(StorageConfig(mode="sqlite_only", db_path=db), root=root)
            original = _install_storage_manager(manager)
            collector = _collector(root)

            try:
                with (
                    patch("ui.state_collector._process_running", return_value=True),
                    patch("ui.state_collector.time.time", return_value=_ts("2026-05-08T10:01:00")),
                ):
                    snapshot = collector.collect()
            finally:
                manager.close()
                _restore_storage_manager(original)

            self.assertEqual(snapshot.workers[0].alpha_id, "alpha-sqlite")


def _collector(root: Path) -> StateCollector:
    import ui.log_stream as log_stream
    import ui.state_collector as state_collector

    state_collector.PID_FILE = root / "logs" / "workflow_active.pid"
    state_collector.STATE_LOG_FILE = root / "logs" / "workflow_state.jsonl"
    state_collector.ITERATION_LOG_FILE = root / "iteration_log.csv"
    log_stream.DEFAULT_LOG_PATHS = [
        root / "workflow.log",
        root / "logs" / "workflow_state.jsonl",
        root / "reward_shadow_logs" / "reward_shadow.jsonl",
        root / "migration_logs" / "migration_events.jsonl",
        root / "iteration_log.csv",
    ]
    return StateCollector(root=root, cache_path=root / "state_cache.json")


def _install_storage_manager(manager: StorageManager):
    import wq_workflow.storage.manager as manager_module

    original = manager_module._MANAGER
    manager_module._MANAGER = manager
    return original


def _restore_storage_manager(original) -> None:
    import wq_workflow.storage.manager as manager_module

    manager_module._MANAGER = original


def _seed_runtime(root: Path) -> None:
    (root / "logs").mkdir(parents=True)
    (root / "memory" / "evolution").mkdir(parents=True)
    (root / "memory" / "dashboard_snapshot").mkdir(parents=True)
    (root / "reward_shadow_logs").mkdir(parents=True)
    (root / "migration_logs").mkdir(parents=True)
    (root / "logs" / "workflow_state.jsonl").write_text("", encoding="utf-8")
    candidate_pool = json.dumps([{"alpha_id": "a1", "diversity_score": 0.8, "reward": 1.0, "passed": True}])
    (root / "memory" / "evolution" / "candidate_pool.json").write_text(
        candidate_pool,
        encoding="utf-8",
    )
    (root / "memory" / "dashboard_snapshot" / "candidate_pool.snapshot.json").write_text(
        candidate_pool,
        encoding="utf-8",
    )
    (root / "memory" / "dashboard_snapshot" / "alpha_lineage.snapshot.json").write_text("[]", encoding="utf-8")
    (root / "memory" / "dashboard_snapshot" / "migration_state.snapshot.json").write_text("{}", encoding="utf-8")
    (root / "memory" / "dashboard_snapshot" / "migration_metrics.snapshot.json").write_text("{}", encoding="utf-8")
    (root / "memory" / "evolution" / "alpha_lineage.json").write_text("[]", encoding="utf-8")
    (root / "workflow.log").write_text("", encoding="utf-8")
    (root / "iteration_log.csv").write_text("time,template_file,alpha_name,iteration,stage\n", encoding="utf-8")


def _ts(value: str) -> float:
    return time.mktime(time.strptime(value, "%Y-%m-%dT%H:%M:%S"))


if __name__ == "__main__":
    unittest.main()
