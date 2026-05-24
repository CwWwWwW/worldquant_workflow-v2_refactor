import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from wq_workflow.logger_state import STATE_FATAL, log_recovery_sidecar, log_state_event


class LoggerStateCompatibilityTests(unittest.TestCase):
    def test_extra_fields_are_optional_append_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_log = Path(tmp) / "logs" / "workflow_state.jsonl"

            with patch("wq_workflow.logger_state.STATE_LOG_FILE", state_log):
                payload = log_state_event(
                    STATE_FATAL,
                    alpha_id="alpha-1",
                    state="BROWSER_WATCHDOG",
                    recovery="LEVEL_4_RESTART_BROWSER",
                    error="browser timeout",
                    extra={
                        "event": "BROKEN_EVENT",
                        "alpha_id": "changed-alpha",
                        "recovery": "BROKEN_RECOVERY",
                        "error": "changed error",
                        "recovery_phase": "watchdog",
                        "circuit_breaker": "open",
                        "full_rebuild": True,
                        "browser_generation": 2,
                    },
                )

            self.assertEqual(payload["event"], "STATE_FATAL")
            self.assertEqual(payload["alpha_id"], "alpha-1")
            self.assertEqual(payload["recovery"], "LEVEL_4_RESTART_BROWSER")
            self.assertEqual(payload["error"], "browser timeout")
            self.assertEqual(payload["recovery_phase"], "watchdog")
            self.assertEqual(payload["circuit_breaker"], "open")
            self.assertTrue(payload["full_rebuild"])
            self.assertEqual(payload["browser_generation"], 2)

            rows = [json.loads(line) for line in state_log.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(rows, [payload])

    def test_recovery_sidecar_logs_plain_append_only_messages(self) -> None:
        with self.assertLogs(level="WARNING") as captured:
            log_recovery_sidecar(
                "BrowserRecovery",
                action="FULL_REBUILD",
                alpha_id="alpha-1",
                state="BROWSER_WATCHDOG",
                recovery="LEVEL_4_RESTART_BROWSER",
                browser_generation=2,
            )

        message = "\n".join(captured.output)
        self.assertIn("[BrowserRecovery] action=FULL_REBUILD", message)
        self.assertIn("alpha_id=alpha-1", message)
        self.assertIn("recovery=LEVEL_4_RESTART_BROWSER", message)
        self.assertIn("browser_generation=2", message)


if __name__ == "__main__":
    unittest.main()
