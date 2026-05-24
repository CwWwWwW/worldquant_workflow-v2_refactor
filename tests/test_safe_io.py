import math
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from utils.safe_json import safe_replace
from wq_workflow.candidate_pool import CandidatePool
from wq_workflow.safe_io import append_jsonl, atomic_write_json, finite_float, read_jsonl_tail, safe_read_json
from wq_workflow.storage.manager import StorageConfig, StorageManager


class SafeIoTests(unittest.TestCase):
    def test_atomic_write_json_sanitizes_non_finite_numbers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"

            atomic_write_json(path, {"value": float("nan"), "nested": [float("inf")]})
            payload = safe_read_json(path, {})

            self.assertEqual(payload["value"], 0.0)
            self.assertEqual(payload["nested"], [0.0])

    def test_corrupt_json_is_quarantined_and_backup_used(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            atomic_write_json(path, {"ok": 1})
            path.write_text("{bad", encoding="utf-8")

            payload = safe_read_json(path, {})

            self.assertEqual(payload, {"ok": 1})
            self.assertTrue(list(Path(tmp).glob("state.json.corrupt.*")))

    def test_finite_float_rejects_nan_and_inf(self) -> None:
        self.assertEqual(finite_float("nan", 7.0), 7.0)
        self.assertEqual(finite_float(float("inf"), -1.0), -1.0)
        self.assertTrue(math.isfinite(finite_float("3.5")))

    def test_safe_replace_retries_permission_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "state.tmp"
            dst = Path(tmp) / "state.json"
            src.write_text('{"ok": 1}', encoding="utf-8")
            attempts = {"count": 0}
            original_replace = __import__("os").replace

            def flaky_replace(left: str | Path, right: str | Path) -> None:
                attempts["count"] += 1
                if attempts["count"] < 3:
                    raise PermissionError("busy")
                original_replace(left, right)

            with (
                patch("utils.safe_json.os.replace", side_effect=flaky_replace),
                patch("utils.safe_json.time.sleep", return_value=None),
            ):
                self.assertTrue(safe_replace(src, dst))

            self.assertEqual(attempts["count"], 3)
            self.assertEqual(json.loads(dst.read_text(encoding="utf-8")), {"ok": 1})

    def test_atomic_write_json_final_replace_failure_keeps_old_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            atomic_write_json(path, {"old": 1})

            with (
                patch("utils.safe_json.os.replace", side_effect=PermissionError("busy")),
                patch("utils.safe_json.time.sleep", return_value=None),
            ):
                atomic_write_json(path, {"new": 2})

            self.assertEqual(safe_read_json(path, {}), {"old": 1})
            self.assertFalse(list(Path(tmp).glob("*.tmp")))

    def test_candidate_pool_concurrent_read_write_never_half_writes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "candidate_pool.json"
            pool = CandidatePool(path, max_size=50)
            errors: list[Exception] = []

            def writer(index: int) -> None:
                try:
                    pool.add_candidate(
                        alpha_id=f"a{index}",
                        expression=f"rank(ts_mean(close, {index + 2}))",
                        metrics={"sharpe": float(index)},
                        reward=float(index) / 10,
                    )
                except Exception as exc:
                    errors.append(exc)

            def reader() -> None:
                try:
                    for _ in range(100):
                        data = safe_read_json(path, [])
                        if not isinstance(data, list):
                            raise AssertionError("candidate pool is not a list")
                except Exception as exc:
                    errors.append(exc)

            threads = [threading.Thread(target=writer, args=(index,)) for index in range(20)]
            threads.extend(threading.Thread(target=reader) for _ in range(4))
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

            self.assertEqual(errors, [])
            self.assertIsInstance(safe_read_json(path, []), list)

    def test_append_jsonl_hybrid_writes_sqlite_and_legacy_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manager = StorageManager(
                StorageConfig(mode="hybrid", db_path=root / "runtime" / "db" / "workflow.db", legacy_export=True),
                root=root,
            )
            original = _install_storage_manager(manager)
            try:
                path = root / "logs" / "workflow_state.jsonl"
                append_jsonl(path, {"time": "2026-05-08T10:00:00", "event": "STATE_ENTER", "alpha_id": "a1", "state": "WAIT_RESULT"})
                self.assertTrue(manager.flush(timeout=5.0))

                self.assertEqual(read_jsonl_tail(path, limit=10)[-1]["alpha_id"], "a1")
                self.assertIn("a1", path.read_text(encoding="utf-8"))
            finally:
                manager.close()
                _restore_storage_manager(original)

    def test_append_jsonl_sqlite_only_keeps_read_api_without_legacy_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manager = StorageManager(
                StorageConfig(mode="sqlite_only", db_path=root / "runtime" / "db" / "workflow.db", legacy_export=False),
                root=root,
            )
            original = _install_storage_manager(manager)
            try:
                path = root / "logs" / "workflow_state.jsonl"
                append_jsonl(path, {"time": "2026-05-08T10:00:00", "event": "STATE_ENTER", "alpha_id": "a1", "state": "WAIT_RESULT"})
                self.assertTrue(manager.flush(timeout=5.0))

                self.assertEqual(read_jsonl_tail(path, limit=10)[-1]["alpha_id"], "a1")
                self.assertFalse(path.exists())
            finally:
                manager.close()
                _restore_storage_manager(original)

    def test_append_jsonl_jsonl_only_uses_legacy_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manager = StorageManager(StorageConfig(mode="jsonl_only", db_path=root / "runtime" / "db" / "workflow.db"), root=root)
            original = _install_storage_manager(manager)
            try:
                path = root / "logs" / "workflow_state.jsonl"
                append_jsonl(path, {"event": "STATE_ENTER", "alpha_id": "a1"})

                self.assertEqual(read_jsonl_tail(path, limit=10)[-1]["alpha_id"], "a1")
                self.assertTrue(path.exists())
            finally:
                manager.close()
                _restore_storage_manager(original)


def _install_storage_manager(manager: StorageManager):
    import wq_workflow.storage.manager as manager_module

    original = manager_module._MANAGER
    manager_module._MANAGER = manager
    return original


def _restore_storage_manager(original) -> None:
    import wq_workflow.storage.manager as manager_module

    manager_module._MANAGER = original


if __name__ == "__main__":
    unittest.main()
