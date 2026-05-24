import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from wq_workflow.models import WorkflowConfig
from wq_workflow.templates import split_and_store_templates


class _FakeDeepSeek:
    def __init__(self, templates):
        self.templates = templates
        self.calls = []

    async def split_templates(self, raw_text, max_count):
        self.calls.append((raw_text, max_count))
        return self.templates


class TemplateSplitFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_full_file_is_sent_once_and_ds_results_are_saved_without_filtering(self) -> None:
        raw_text = "first template\n\nsecond template with {datafield}\n\nalpha = returns"
        ds = _FakeDeepSeek(
            [
                {"name": "duplicate_a", "code": "rank(close)", "reason": "ds"},
                {"name": "duplicate_b", "code": "rank(close)", "reason": "ds duplicate"},
                {"name": "placeholder", "code": "rank({datafield})", "reason": "needs later repair"},
                {"name": "reserved", "code": "alpha = returns\nalpha", "reason": "needs later repair"},
            ]
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            template_dir = root / "templates"
            template_dir.mkdir()
            manifest = template_dir / "last_split_manifest.json"
            input_file = root / "input.txt"
            input_file.write_text(raw_text, encoding="utf-8")

            with patch("wq_workflow.templates.TEMPLATE_DIR", template_dir), patch(
                "wq_workflow.templates.SPLIT_MANIFEST_FILE", manifest
            ), patch("wq_workflow.templates.ROOT", root):
                items = await split_and_store_templates(
                    ds,
                    WorkflowConfig(max_templates=0),
                    extra_files=[str(input_file)],
                )

        self.assertEqual([(raw_text, None)], ds.calls)
        self.assertEqual(4, len(items))
        self.assertEqual(["duplicate_a", "duplicate_b", "placeholder", "reserved"], [item.name for item in items])
        self.assertEqual(["rank(close)", "rank(close)", "rank({datafield})", "alpha = returns\nalpha"], [item.code for item in items])

    async def test_empty_deepseek_result_raises_without_local_fallback(self) -> None:
        ds = _FakeDeepSeek([])

        with tempfile.TemporaryDirectory() as temp_dir:
            input_file = Path(temp_dir) / "input.txt"
            input_file.write_text("rank(close)", encoding="utf-8")

            with self.assertRaisesRegex(RuntimeError, "DeepSeek 未返回可用模板 JSON"):
                await split_and_store_templates(
                    ds,
                    WorkflowConfig(max_templates=0),
                    extra_files=[str(input_file)],
                )

        self.assertEqual([("rank(close)", None)], ds.calls)


if __name__ == "__main__":
    unittest.main()
