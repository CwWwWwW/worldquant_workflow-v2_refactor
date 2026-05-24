import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from wq_workflow.candidate_pool import CandidatePool
from wq_workflow.models import QualityReport
from wq_workflow.orchestrator import record_pending_mutation_result
from wq_workflow.paths import ITERATION_LOG_FIELDS, append_csv
from wq_workflow.reward_engine import RewardEngine
from wq_workflow.storage.repository import CandidatePoolRepository
from wq_workflow.storage.schema import initialize_schema
from wq_workflow.storage.sqlite_store import connect_db
from wq_workflow.memory_manager import EvolutionMemory


PLATFORM_SC = {"status": "complete", "max": -0.0402, "min": -0.5418, "abs_max": 0.5418}


class CandidatePoolPlatformScTests(unittest.TestCase):
    def test_add_candidate_accepts_and_persists_platform_sc_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "candidate_pool.json"
            pool = CandidatePool(path)
            with patch("wq_workflow.storage.get_storage_manager") as storage:
                storage.return_value.write_candidate_record.return_value = None
                candidate = pool.add_candidate(
                    alpha_id="a1",
                    expression="rank(close)",
                    metrics={"sharpe": 1.2, "fitness": 1.0},
                    reward=1.0,
                    platform_sc_status="complete",
                    platform_sc_max=-0.0402,
                    platform_sc_min=-0.5418,
                    platform_sc_abs_max=0.5418,
                    platform_sc_payload=PLATFORM_SC,
                )

            self.assertEqual(candidate["platform_sc_status"], "complete")
            self.assertEqual(candidate["platform_sc_max"], -0.0402)
            self.assertEqual(candidate["platform_sc_min"], -0.5418)
            self.assertEqual(candidate["platform_sc_abs_max"], 0.5418)
            self.assertEqual(candidate["platform_sc"], PLATFORM_SC)
            rows = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(rows[0]["platform_sc"]["status"], "complete")

    def test_legacy_candidate_pool_without_platform_sc_still_selects_parent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "candidate_pool.json"
            path.write_text(
                json.dumps(
                    [
                        {
                            "alpha_id": "legacy",
                            "expression": "rank(close)",
                            "metrics": {"sharpe": 1.0, "fitness": 0.5},
                            "reward": 0.2,
                            "timestamp": "2026-05-01T00:00:00",
                        }
                    ]
                ),
                encoding="utf-8",
            )
            pool = CandidatePool(path)

            self.assertEqual(pool.get_top_sharpe(1)[0]["alpha_id"], "legacy")
            self.assertEqual(pool.select_next_parent()["alpha_id"], "legacy")

    def test_optional_payload_and_non_complete_statuses_are_safe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pool = CandidatePool(Path(tmp) / "candidate_pool.json")
            with patch("wq_workflow.storage.get_storage_manager") as storage:
                storage.return_value.write_candidate_record.return_value = None
                timeout = pool.add_candidate(
                    alpha_id="timeout",
                    expression="rank(open)",
                    metrics={"sharpe": 0.1},
                    platform_sc_status="timeout",
                    platform_sc_payload=None,
                )
                error = pool.add_candidate(
                    alpha_id="error",
                    expression="rank(volume)",
                    metrics={"sharpe": 0.2},
                    platform_sc_status="error",
                    platform_sc_payload={"status": "error", "error": "boom"},
                )

            self.assertEqual(timeout["platform_sc_status"], "timeout")
            self.assertNotIn("platform_sc", timeout)
            self.assertEqual(error["platform_sc_status"], "error")
            self.assertEqual(error["platform_sc"]["error"], "boom")

    def test_candidate_pool_repository_raw_payload_keeps_platform_sc(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            conn = connect_db(Path(tmp) / "workflow.db")
            try:
                initialize_schema(conn)
                payload = {
                    "alpha_id": "a1",
                    "expression": "rank(close)",
                    "reward": 0.7,
                    "platform_sc_status": "complete",
                    "platform_sc_abs_max": 0.5418,
                    "platform_sc": PLATFORM_SC,
                }
                CandidatePoolRepository(conn).upsert_candidate(payload)
                raw = conn.execute("SELECT raw_payload FROM candidate_pool WHERE alpha_id = 'a1'").fetchone()[0]
                stored = json.loads(raw)
                self.assertEqual(stored["platform_sc_status"], "complete")
                self.assertEqual(stored["platform_sc_abs_max"], 0.5418)
                self.assertEqual(stored["platform_sc"]["min"], -0.5418)
            finally:
                conn.close()

    def test_old_iteration_csv_is_extended_without_dropping_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "iteration_log.csv"
            path.write_text("time,alpha_name,metrics_json\nold,a0,{}\n", encoding="utf-8")

            append_csv(
                path,
                ITERATION_LOG_FIELDS,
                {
                    "time": "new",
                    "alpha_name": "a1",
                    "metrics_json": "{}",
                    "platform_sc_status": "complete",
                    "platform_sc_abs_max": 0.5418,
                    "platform_sc_json": json.dumps(PLATFORM_SC),
                },
            )

            with path.open("r", encoding="utf-8-sig", newline="") as fh:
                rows = list(csv.DictReader(fh))
            self.assertEqual(rows[0]["time"], "old")
            self.assertEqual(rows[1]["platform_sc_status"], "complete")
            self.assertEqual(rows[1]["platform_sc_json"], json.dumps(PLATFORM_SC))

    def test_record_pending_mutation_result_passes_platform_sc_in_both_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pool = CandidatePool(root / "candidate_pool.json", max_size=10)
            memory = EvolutionMemory(
                lineage_file=root / "alpha_lineage.json",
                failures_file=root / "failures.json",
                statistics_file=root / "operator_statistics.json",
            )
            reward_engine = RewardEngine(
                enable_migration=False,
                enable_survival_memory=False,
                enable_pending_reward=False,
                enable_template_governance=False,
            )
            quality = QualityReport(passed=True, status="PASS")
            metrics = {
                "sharpe": 1.0,
                "fitness": 0.8,
                "platform_sc_status": "complete",
                "platform_sc_max": -0.0402,
                "platform_sc_min": -0.5418,
                "platform_sc_abs_max": 0.5418,
            }

            with patch("wq_workflow.storage.get_storage_manager") as storage:
                storage.return_value.write_candidate_record.return_value = None
                record_pending_mutation_result(
                    pending=None,
                    alpha_name="alpha",
                    iteration=1,
                    code="rank(close)",
                    metrics=dict(metrics),
                    quality=quality,
                    reward_engine=reward_engine,
                    evolution_memory=memory,
                    candidate_pool=pool,
                    v2_enabled=False,
                    platform_sc=PLATFORM_SC,
                )
                record_pending_mutation_result(
                    pending={
                        "parent_id": "alpha:1",
                        "expression_before": "rank(close)",
                        "metrics_before": {"sharpe": 0.5, "fitness": 0.4},
                        "mutation_type": "window",
                    },
                    alpha_name="alpha",
                    iteration=2,
                    code="rank(ts_mean(close, 3))",
                    metrics=dict(metrics),
                    quality=quality,
                    reward_engine=reward_engine,
                    evolution_memory=memory,
                    candidate_pool=pool,
                    v2_enabled=False,
                    platform_sc=PLATFORM_SC,
                )

            rows = {row["alpha_id"]: row for row in json.loads((root / "candidate_pool.json").read_text(encoding="utf-8"))}
            self.assertEqual(rows["alpha:1"]["platform_sc"]["status"], "complete")
            self.assertEqual(rows["alpha:2"]["platform_sc_abs_max"], 0.5418)


if __name__ == "__main__":
    unittest.main()
