import sqlite3
import tempfile
import unittest
from pathlib import Path

from wq_workflow.storage.schema import SCHEMA_VERSION, initialize_schema
from wq_workflow.storage.sqlite_store import connect_db


class StorageSchemaTests(unittest.TestCase):
    def test_schema_initializes_with_wal_and_indexes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "workflow.db"
            conn = connect_db(db)
            try:
                initialize_schema(conn)
                initialize_schema(conn)

                journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
                self.assertEqual(str(journal_mode).lower(), "wal")

                tables = {
                    row[0]
                    for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    ).fetchall()
                }
                self.assertIn("alpha_runs", tables)
                self.assertIn("lineage", tables)
                self.assertIn("events", tables)
                self.assertIn("policy_memory", tables)
                self.assertEqual(SCHEMA_VERSION, 2)
                for table in {
                    "evolution_population",
                    "evolution_generations",
                    "evolution_policy_actions",
                    "evolution_decisions",
                    "alpha_graph_edges",
                    "lineage_values",
                    "simulator_observations",
                    "evolution_meta",
                }:
                    self.assertIn(table, tables)

                indexes = {
                    row[0]
                    for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'index'"
                    ).fetchall()
                }
                self.assertIn("idx_alpha_id", indexes)
                self.assertIn("idx_events_replay", indexes)
                self.assertIn("idx_evolution_population_score", indexes)
                self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 2)
            finally:
                conn.close()

    def test_storage_migration_v1_to_v2_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "workflow.db"
            conn = connect_db(db)
            try:
                initialize_schema(conn)
                conn.execute("INSERT INTO alpha_runs (alpha_id) VALUES ('legacy')")
                conn.execute("PRAGMA user_version = 1")

                initialize_schema(conn)
                initialize_schema(conn)

                self.assertEqual(conn.execute("SELECT alpha_id FROM alpha_runs").fetchone()[0], "legacy")
                self.assertIsNotNone(conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='evolution_population'").fetchone())
                self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 2)
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()
