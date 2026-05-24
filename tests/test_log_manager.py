import json
import os
import tempfile
import unittest
from pathlib import Path

from log_manager import export_logs, import_logs, replay_logs, verify_integrity
from log_manager.archive import archive_logs
from wq_workflow.storage.repository import EventRepository
from wq_workflow.storage.schema import initialize_schema
from wq_workflow.storage.sqlite_store import connect_db


class LogManagerTests(unittest.TestCase):
    def test_export_manifest_integrity_replay_and_offline_import(self) -> None:
        with tempfile.TemporaryDirectory() as src_tmp, tempfile.TemporaryDirectory() as out_tmp, tempfile.TemporaryDirectory() as dst_tmp:
            root = Path(src_tmp)
            _seed_logs(root)

            result = export_logs(root, Path(out_tmp), alpha_id="alpha-1", archive_format="", resume=False)

            export_dir = Path(result.export_dir)
            manifest = json.loads((export_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["schema_version"], "log_manager_manifest_v1")
            self.assertTrue(any(item["relative_path"] == "logs/workflow_state.jsonl" for item in manifest["files"]))
            exported_state = (export_dir / "files" / "logs" / "workflow_state.jsonl").read_text(encoding="utf-8")
            self.assertIn("alpha-1", exported_state)
            self.assertNotIn("alpha-2", exported_state)

            report = verify_integrity(export_dir)
            self.assertEqual(report.status, "ok")

            events = replay_logs(export_dir)
            self.assertTrue(any(event.source == "simulate" and event.alpha_id == "alpha-1" for event in events))
            self.assertTrue(any(event.source == "reward" and event.alpha_id == "alpha-1" for event in events))

            imported = import_logs(export_dir, Path(dst_tmp), mode="offline")
            self.assertIn("logs/workflow_state.jsonl", imported.imported_files)
            self.assertTrue((Path(imported.target_dir) / "manifest.json").exists())

    def test_archive_and_incremental_import(self) -> None:
        with tempfile.TemporaryDirectory() as src_tmp, tempfile.TemporaryDirectory() as out_tmp, tempfile.TemporaryDirectory() as dst_tmp:
            root = Path(src_tmp)
            _seed_logs(root)
            result = export_logs(root, Path(out_tmp), archive_format="", resume=False)
            archive_paths = archive_logs(result.export_dir, format="zip", volume_size_mb=1024)
            self.assertEqual(len(archive_paths), 1)
            self.assertTrue(Path(archive_paths[0]).exists())
            archive_report = verify_integrity(archive_paths[0])
            self.assertEqual(archive_report.status, "ok")

            target = Path(dst_tmp)
            (target / "logs").mkdir(parents=True)
            (target / "logs" / "workflow_state.jsonl").write_text("", encoding="utf-8")
            imported = import_logs(Path(result.export_dir), target, mode="incremental")

            self.assertIn("logs/workflow_state.jsonl", imported.imported_files)
            text = (target / "logs" / "workflow_state.jsonl").read_text(encoding="utf-8")
            self.assertIn("alpha-1", text)

    def test_incremental_import_refused_while_workflow_running(self) -> None:
        with tempfile.TemporaryDirectory() as src_tmp, tempfile.TemporaryDirectory() as out_tmp, tempfile.TemporaryDirectory() as dst_tmp:
            root = Path(src_tmp)
            _seed_logs(root)
            result = export_logs(root, Path(out_tmp), archive_format="", resume=False)

            target = Path(dst_tmp)
            (target / "logs").mkdir(parents=True)
            (target / "logs" / "workflow_active.pid").write_text(str(os.getpid()), encoding="utf-8")
            imported = import_logs(Path(result.export_dir), target, mode="incremental")

            self.assertIn("workflow is running", " ".join(imported.errors))

    def test_integrity_reports_corrupt_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as src_tmp, tempfile.TemporaryDirectory() as out_tmp:
            root = Path(src_tmp)
            _seed_logs(root)
            result = export_logs(root, Path(out_tmp), archive_format="", resume=False)
            state = Path(result.export_dir) / "files" / "logs" / "workflow_state.jsonl"
            with state.open("a", encoding="utf-8") as fh:
                fh.write("{bad json\n")

            report = verify_integrity(result.export_dir)

            self.assertEqual(report.status, "failed")
            self.assertTrue(any("jsonl line" in error for error in report.errors))

    def test_export_and_replay_include_sqlite_snapshot_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as src_tmp, tempfile.TemporaryDirectory() as out_tmp:
            root = Path(src_tmp)
            _seed_logs(root)
            db = root / "runtime" / "db" / "workflow.db"
            conn = connect_db(db)
            try:
                initialize_schema(conn)
                EventRepository(conn, root=root).insert_event(
                    root / "logs" / "workflow_state.jsonl",
                    {"time": "2026-05-08T10:05:00", "event": "STATE_PROGRESS", "alpha_id": "alpha-sqlite", "state": "WAIT_RESULT"},
                )
            finally:
                conn.close()

            result = export_logs(root, Path(out_tmp), archive_format="", resume=False)
            export_dir = Path(result.export_dir)

            self.assertTrue((export_dir / "files" / "runtime" / "db" / "workflow_snapshot.json").exists())
            replayed = replay_logs(export_dir)
            self.assertTrue(any(event.alpha_id == "alpha-sqlite" for event in replayed))

    def test_replay_and_import_accept_legacy_and_optional_recovery_fields(self) -> None:
        with tempfile.TemporaryDirectory() as src_tmp, tempfile.TemporaryDirectory() as out_tmp, tempfile.TemporaryDirectory() as dst_tmp:
            root = Path(src_tmp)
            _seed_logs(root)
            state_log = root / "logs" / "workflow_state.jsonl"
            state_log.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "time": "2026-05-07T16:08:56",
                                "event": "STATE_FATAL",
                                "alpha_id": "alpha-legacy",
                                "state": "WAIT_RESULT",
                                "duration": 0.0,
                                "retry": 0,
                                "recovery": "RESTART_TASK",
                                "error": "Invalid number of inputs",
                            }
                        ),
                        json.dumps(
                            {
                                "time": "2026-05-11T12:30:20",
                                "event": "STATE_FATAL",
                                "alpha_id": "alpha-new",
                                "state": "BROWSER_WATCHDOG",
                                "duration": 5.0,
                                "retry": 0,
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
            (root / "workflow.log").write_text(
                "2026-05-11 12:30:20,000 [INFO] FSM STATE_FATAL "
                '{"time":"2026-05-11T12:30:20","event":"STATE_FATAL","alpha_id":"alpha-new","state":"BROWSER_WATCHDOG","recovery":"LEVEL_4_RESTART_BROWSER","error":"browser timeout"}\n'
                "2026-05-11 12:30:20,001 [WARNING] [BrowserRecovery] action=FULL_REBUILD alpha_id=alpha-new recovery=LEVEL_4_RESTART_BROWSER\n"
                "2026-05-11 12:30:20,002 [WARNING] [FullRebuild] action=RESTART_BROWSER alpha_id=alpha-new recovery=LEVEL_4_RESTART_BROWSER\n"
                "2026-05-11 12:30:20,003 [WARNING] [CircuitBreaker] action=OPEN_BROWSER_WATCHDOG alpha_id=alpha-new recovery=LEVEL_4_RESTART_BROWSER\n",
                encoding="utf-8",
            )

            result = export_logs(root, Path(out_tmp), archive_format="", resume=False)
            export_dir = Path(result.export_dir)
            replayed = replay_logs(export_dir)
            fatal_events = [event for event in replayed if event.event_type == "STATE_FATAL"]

            self.assertTrue(any(event.alpha_id == "alpha-legacy" and event.payload["recovery"] == "RESTART_TASK" for event in fatal_events))
            self.assertTrue(any(event.alpha_id == "alpha-new" and event.payload.get("full_rebuild") is True for event in fatal_events))
            self.assertTrue(any(event.event_type == "log" and "[BrowserRecovery]" in event.payload.get("message", "") for event in replayed))

            imported = import_logs(export_dir, Path(dst_tmp), mode="offline")

            self.assertIn("logs/workflow_state.jsonl", imported.imported_files)
            imported_state = Path(imported.target_dir) / "files" / "logs" / "workflow_state.jsonl"
            self.assertIn("alpha-legacy", imported_state.read_text(encoding="utf-8"))


def _seed_logs(root: Path) -> None:
    (root / "logs").mkdir(parents=True)
    (root / "reward_shadow_logs").mkdir(parents=True)
    (root / "migration_logs").mkdir(parents=True)
    (root / "memory" / "evolution").mkdir(parents=True)
    (root / "memory" / "statistics").mkdir(parents=True)
    (root / "memory" / "failure_patterns").mkdir(parents=True)
    (root / "workflow.log").write_text(
        "2026-05-08 10:00:00,000 [INFO] FSM STATE_ENTER alpha-1\n",
        encoding="utf-8",
    )
    (root / "logs" / "workflow_state.jsonl").write_text(
        json.dumps({"time": "2026-05-08T10:00:00", "event": "STATE_ENTER", "alpha_id": "alpha-1", "state": "WAIT_RESULT"})
        + "\n"
        + json.dumps({"time": "2026-05-08T10:01:00", "event": "STATE_ENTER", "alpha_id": "alpha-2", "state": "WAIT_RESULT"})
        + "\n",
        encoding="utf-8",
    )
    (root / "reward_shadow_logs" / "reward_shadow.jsonl").write_text(
        json.dumps(
            {
                "timestamp": "2026-05-08T10:02:00",
                "alpha_id": "alpha-1",
                "legacy_reward": 1.0,
                "v2_reward": 1.2,
                "final_reward": 1.0,
                "state": "shadow",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "migration_logs" / "migration_events.jsonl").write_text(
        json.dumps({"timestamp": "2026-05-08T10:03:00", "event": "transition", "alpha_id": "alpha-1"})
        + "\n",
        encoding="utf-8",
    )
    (root / "memory" / "evolution" / "candidate_pool.json").write_text(
        json.dumps([{"alpha_id": "alpha-1", "timestamp": "2026-05-08T10:04:00", "reward": 1.0}]),
        encoding="utf-8",
    )
    (root / "memory" / "evolution" / "alpha_lineage.json").write_text("[]", encoding="utf-8")
    (root / "memory" / "statistics" / "operator_statistics.json").write_text("{}", encoding="utf-8")
    (root / "memory" / "failure_patterns" / "failures.json").write_text("[]", encoding="utf-8")
    (root / "iteration_log.csv").write_text("time,template_file,alpha_name,iteration,stage\n", encoding="utf-8")
    (root / "favorite_alphas.csv").write_text("time,template_file,alpha_name,code,metrics_json,quality_json,screenshot\n", encoding="utf-8")
    (root / "local_alpha_library.csv").write_text("alpha_id,created_at,md5,code,core_structure,metrics,returns_path\n", encoding="utf-8")
    (root / "correlation_check.log").write_text("", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
