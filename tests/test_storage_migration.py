import json
import tempfile
import unittest
from pathlib import Path

from wq_workflow.storage.migrate_jsonl import migrate_root
from wq_workflow.storage.repository import EventRepository, LineageRepository
from wq_workflow.storage.schema import initialize_schema
from wq_workflow.storage.sqlite_store import connect_db


class StorageMigrationTests(unittest.TestCase):
    def test_migration_skips_bad_lines_and_is_incremental(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            logs = root / "logs"
            memory = root / "memory" / "evolution"
            logs.mkdir(parents=True)
            memory.mkdir(parents=True)
            state = logs / "workflow_state.jsonl"
            state.write_text(
                json.dumps({"time": "2026-05-08T10:00:00", "event": "STATE_ENTER", "alpha_id": "a1", "state": "WAIT_RESULT"})
                + "\n"
                + "{bad json\n",
                encoding="utf-8",
            )
            (memory / "alpha_lineage.json").write_text(
                json.dumps([{"alpha_id": "a2", "parent_id": "a1", "mutation_type": "window"}]),
                encoding="utf-8",
            )
            db = root / "runtime" / "db" / "workflow.db"

            first = migrate_root(root, db)
            second = migrate_root(root, db)

            self.assertEqual(first.imported_events, 1)
            self.assertEqual(first.skipped_bad_lines, 1)
            self.assertGreaterEqual(second.skipped_existing_lines, 2)

            conn = connect_db(db)
            try:
                initialize_schema(conn)
                self.assertEqual(len(EventRepository(conn, root=root).tail_for_path(state, limit=10)), 1)
                self.assertEqual(LineageRepository(conn).get_parents("a2")[0]["parent_alpha"], "a1")
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()
