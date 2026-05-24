import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from wq_workflow import cli


class CliLogMenuTests(unittest.TestCase):
    def test_main_menu_export_option_calls_log_export_menu(self) -> None:
        with patch("wq_workflow.cli.ensure_runtime_files"), patch("wq_workflow.cli.print_banner"), patch(
            "builtins.input", side_effect=["5", "0"]
        ), patch("wq_workflow.cli.log_export_menu", return_value=0) as export_menu:
            result = cli.menu_command()

        self.assertEqual(result, 0)
        export_menu.assert_called_once()

    def test_main_menu_import_option_calls_log_import_menu(self) -> None:
        with patch("wq_workflow.cli.ensure_runtime_files"), patch("wq_workflow.cli.print_banner"), patch(
            "builtins.input", side_effect=["6", "0"]
        ), patch("wq_workflow.cli.log_import_menu", return_value=0) as import_menu:
            result = cli.menu_command()

        self.assertEqual(result, 0)
        import_menu.assert_called_once()

    def test_log_export_menu_uses_safe_defaults(self) -> None:
        result = SimpleNamespace(
            export_id="exp1",
            export_dir="out/exp1",
            manifest_path="out/exp1/manifest.json",
            files_count=3,
            total_bytes=1024,
            archive_paths=[],
            warnings=[],
        )
        with patch("wq_workflow.cli.ensure_runtime_files"), patch(
            "builtins.input",
            side_effect=["", "", "", "", "", "", ""],
        ), patch("log_manager.export_logs", return_value=result) as export_logs:
            status = cli.log_export_menu()

        self.assertEqual(status, 0)
        args, kwargs = export_logs.call_args
        self.assertEqual(args[0], cli.ROOT)
        self.assertEqual(args[1], cli.ROOT / "log_exports")
        self.assertEqual(kwargs["archive_format"], "zip")
        self.assertIsNone(kwargs["alpha_id"])
        self.assertIsNone(kwargs["since"])
        self.assertIsNone(kwargs["until"])
        self.assertIsNone(kwargs["task_id"])
        self.assertIsNone(kwargs["worker_id"])

    def test_log_import_menu_uses_offline_default(self) -> None:
        result = SimpleNamespace(
            mode="offline",
            target_dir="log_imports/exp1",
            imported_files=["workflow.log"],
            skipped_files=[],
            warnings=[],
            errors=[],
        )
        with patch("wq_workflow.cli.ensure_runtime_files"), patch(
            "builtins.input",
            side_effect=["log_exports/exp1", ""],
        ), patch("log_manager.import_logs", return_value=result) as import_logs:
            status = cli.log_import_menu()

        self.assertEqual(status, 0)
        args, kwargs = import_logs.call_args
        self.assertEqual(args[0], cli.ROOT / "log_exports" / "exp1")
        self.assertEqual(args[1], cli.ROOT)
        self.assertEqual(kwargs["mode"], "offline")

    def test_log_import_restore_requires_confirmation(self) -> None:
        with patch("wq_workflow.cli.ensure_runtime_files"), patch(
            "builtins.input",
            side_effect=["log_exports/exp1", "4", "no"],
        ), patch("log_manager.import_logs") as import_logs:
            status = cli.log_import_menu()

        self.assertEqual(status, 0)
        import_logs.assert_not_called()


if __name__ == "__main__":
    unittest.main()
