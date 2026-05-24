import asyncio
import unittest

from wq_workflow.watchdog import WatchdogTimeout, step


class WatchdogTests(unittest.IsolatedAsyncioTestCase):
    async def test_step_returns_value_before_timeout(self) -> None:
        async def quick() -> str:
            await asyncio.sleep(0)
            return "ok"

        self.assertEqual(await step("quick", quick(), 1), "ok")

    async def test_step_raises_watchdog_timeout(self) -> None:
        async def slow() -> None:
            await asyncio.sleep(0.2)

        with self.assertRaises(WatchdogTimeout):
            await step("slow", slow(), 0.01)


if __name__ == "__main__":
    unittest.main()
