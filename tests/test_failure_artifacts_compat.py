import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from wq_workflow.failure_artifacts import capture_failure_artifacts


class FakePage:
    def __init__(self) -> None:
        self._closed = False

    def is_closed(self) -> bool:
        return self._closed

    async def screenshot(self, *, path: str, full_page: bool) -> None:
        Path(path).write_bytes(b"png")

    async def content(self) -> str:
        return "<html>failure</html>"


class FakeTracing:
    async def stop(self, *, path: str) -> None:
        Path(path).write_bytes(b"trace")


class FakeContext:
    tracing = FakeTracing()


class FailureArtifactsCompatibilityTests(unittest.IsolatedAsyncioTestCase):
    async def test_failure_artifacts_keep_legacy_directories_and_stem(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            failure_dir = root / "logs" / "failures"
            trace_dir = root / "logs" / "traces"

            with (
                patch("wq_workflow.failure_artifacts.FAILURE_DIR", failure_dir),
                patch("wq_workflow.failure_artifacts.TRACE_DIR", trace_dir),
                patch("wq_workflow.failure_artifacts.now_ts", return_value="20260511_123020"),
            ):
                artifacts = await capture_failure_artifacts(
                    FakePage(),
                    alpha_id="Auto Alpha 001",
                    state="BROWSER_WATCHDOG",
                    context=FakeContext(),
                )

            self.assertEqual(Path(artifacts.screenshot).parent, failure_dir)
            self.assertEqual(Path(artifacts.html).parent, failure_dir)
            self.assertEqual(Path(artifacts.trace).parent, trace_dir)
            self.assertEqual(Path(artifacts.screenshot).name, "Auto_Alpha_001_BROWSER_WATCHDOG_20260511_123020.png")
            self.assertEqual(Path(artifacts.html).name, "Auto_Alpha_001_BROWSER_WATCHDOG_20260511_123020.html")
            self.assertEqual(Path(artifacts.trace).name, "Auto_Alpha_001_BROWSER_WATCHDOG_20260511_123020.zip")


if __name__ == "__main__":
    unittest.main()
