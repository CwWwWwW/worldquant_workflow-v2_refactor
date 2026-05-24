import tempfile
import unittest
from pathlib import Path

from ui.log_stream import LogStreamer


class LogStreamerTests(unittest.TestCase):
    def test_incremental_tail_and_source_classification(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "workflow.log"
            log.write_text("2026-05-08 10:00:00,000 [INFO] FSM STATE_ENTER alpha\n", encoding="utf-8")
            streamer = LogStreamer([log], max_lines=10)

            first = streamer.poll()
            self.assertEqual(len(first), 1)
            self.assertEqual(first[0].source, "simulate")

            with log.open("a", encoding="utf-8") as fh:
                fh.write("2026-05-08 10:00:01,000 [WARNING] DeepSeek repair needed\n")

            second = streamer.poll()
            self.assertEqual(len(second), 2)
            self.assertEqual(second[-1].level, "WARNING")
            self.assertEqual(second[-1].source, "repair")

    def test_jsonl_migration_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "migration_events.jsonl"
            log.write_text('{"timestamp":"2026-05-08T10:00:00","action":"rollback"}\n', encoding="utf-8")
            lines = LogStreamer([log]).poll()

            self.assertEqual(lines[0].source, "migration")
            self.assertEqual(lines[0].level, "WARNING")

    def test_recovery_sidecar_messages_do_not_replace_fsm_logs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "workflow.log"
            log.write_text(
                "2026-05-11 12:30:20,000 [INFO] FSM STATE_FATAL "
                '{"time":"2026-05-11T12:30:20","event":"STATE_FATAL","alpha_id":"alpha-1","state":"BROWSER_WATCHDOG","recovery":"LEVEL_4_RESTART_BROWSER","error":"browser timeout"}\n'
                "2026-05-11 12:30:20,001 [WARNING] [BrowserRecovery] action=FULL_REBUILD alpha_id=alpha-1 recovery=LEVEL_4_RESTART_BROWSER\n"
                "2026-05-11 12:30:20,002 [WARNING] [FullRebuild] action=RESTART_BROWSER alpha_id=alpha-1 recovery=LEVEL_4_RESTART_BROWSER\n"
                "2026-05-11 12:30:20,003 [WARNING] [CircuitBreaker] action=OPEN_BROWSER_WATCHDOG alpha_id=alpha-1 recovery=LEVEL_4_RESTART_BROWSER\n",
                encoding="utf-8",
            )

            lines = LogStreamer([log], max_lines=10).poll()

            self.assertEqual(len(lines), 4)
            self.assertIn("FSM STATE_FATAL", lines[0].message)
            self.assertNotIn("[BrowserRecovery]", lines[0].message)
            self.assertTrue(all(line.source == "browser" for line in lines[1:]))
            self.assertTrue(any("[BrowserRecovery]" in line.message for line in lines))
            self.assertTrue(any("[FullRebuild]" in line.message for line in lines))
            self.assertTrue(any("[CircuitBreaker]" in line.message for line in lines))


if __name__ == "__main__":
    unittest.main()
