import unittest
from unittest.mock import patch

from wq_workflow.recovery import RecoveryLevel, kill_chromium_processes


class RecoveryTests(unittest.TestCase):
    def test_recovery_levels_are_ordered(self) -> None:
        self.assertLess(RecoveryLevel.LEVEL_1_RELOAD_PAGE.value, RecoveryLevel.LEVEL_2_RECREATE_PAGE.value)
        self.assertLess(RecoveryLevel.LEVEL_2_RECREATE_PAGE.value, RecoveryLevel.LEVEL_3_REBUILD_CONTEXT.value)
        self.assertLess(RecoveryLevel.LEVEL_3_REBUILD_CONTEXT.value, RecoveryLevel.LEVEL_4_RESTART_BROWSER.value)
        self.assertLess(RecoveryLevel.LEVEL_4_RESTART_BROWSER.value, RecoveryLevel.LEVEL_5_KILL_CHROMIUM.value)


class RecoveryExecutionTests(unittest.IsolatedAsyncioTestCase):
    async def test_level_5_without_tracked_pids_does_not_broad_kill(self) -> None:
        with patch("wq_workflow.recovery.subprocess.run") as run:
            await kill_chromium_processes(set())

        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
