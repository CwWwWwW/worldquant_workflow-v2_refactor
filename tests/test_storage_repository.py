import tempfile
import unittest
from pathlib import Path

from wq_workflow.storage.repository import (
    AlphaRepository,
    CandidatePoolRepository,
    EventRepository,
    EvolutionMemoryRepository,
    LineageRepository,
    OperatorStatsRepository,
    StateTransitionRepository,
)
from wq_workflow.storage.evolution_repository import EvolutionDBRepository
from wq_workflow.storage.schema import initialize_schema
from wq_workflow.storage.sqlite_store import connect_db


class StorageRepositoryTests(unittest.TestCase):
    def test_repository_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            conn = connect_db(root / "workflow.db")
            try:
                initialize_schema(conn)
                AlphaRepository(conn).insert_alpha(
                    {"alpha_id": "a1", "expression": "rank(close)", "metrics": {"sharpe": 1.2}, "reward": 0.7}
                )
                self.assertEqual(AlphaRepository(conn).get_alpha("a1")["expression"], "rank(close)")

                LineageRepository(conn).add_lineage(payload={"alpha_id": "a2", "parent_id": "a1", "mutation_type": "window"})
                self.assertEqual(LineageRepository(conn).get_parents("a2")[0]["parent_alpha"], "a1")

                OperatorStatsRepository(conn).replace_from_mapping({"window": {"success_count": 2, "fail_count": 1, "avg_reward": 0.5}})
                self.assertIn("window", OperatorStatsRepository(conn).get_all())

                StateTransitionRepository(conn).add_transition(
                    {"time": "2026-05-08T10:00:00", "event": "STATE_ENTER", "alpha_id": "a1", "state": "WAIT_RESULT"}
                )
                self.assertEqual(StateTransitionRepository(conn).tail(limit=1)[0]["state"], "WAIT_RESULT")

                EvolutionMemoryRepository(conn).set_memory("policy_memory", "k", {"value": 1}, score=1.0)
                self.assertEqual(EvolutionMemoryRepository(conn).get_memory("policy_memory", "k")["value"], 1)

                CandidatePoolRepository(conn).replace_candidates(
                    [{"alpha_id": "a1", "expression": "rank(close)", "reward": 0.7, "passed": True}]
                )
                self.assertEqual(CandidatePoolRepository(conn).list_candidates()[0]["alpha_id"], "a1")

                state_path = root / "logs" / "workflow_state.jsonl"
                EventRepository(conn, root=root).insert_event(
                    state_path,
                    {"time": "2026-05-08T10:00:00", "event": "STATE_PROGRESS", "alpha_id": "a1", "state": "WAIT_RESULT"},
                )
                tail = EventRepository(conn, root=root).tail_for_path(state_path, limit=10)
                self.assertEqual(tail[-1]["event"], "STATE_PROGRESS")

                evolution = EvolutionDBRepository(conn)
                evolution.upsert_population_member(
                    {"alpha_id": "e1", "expression": "rank(close)", "reward": 0.4, "survival_score": 0.7}
                )
                self.assertEqual(evolution.list_population(limit=1)[0]["alpha_id"], "e1")

                evolution.upsert_policy_action(
                    action_type="mutation",
                    action_name="add_decay",
                    context_key="global",
                    reward_delta=0.5,
                    success=True,
                )
                self.assertNotEqual(evolution.get_policy_weights("mutation")["add_decay"], 1.0)

                evolution.record_decision({"decision_type": "mutation_selection", "action_type": "mutation", "action_name": "add_decay"})
                evolution.upsert_graph_edge("operator_pair", "rank", "ts_mean", reward=0.2, success=True, payload={})
                evolution.upsert_lineage_value("e1", {"current_reward": 0.4, "future_reward": 0.2, "long_term_value": 0.3})
                evolution.record_simulator_observation({"alpha_id": "e1", "expression": "rank(close)", "simulator_score": 0.5})
                self.assertEqual(evolution.list_graph_edges("operator_pair")[0]["src"], "rank")
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()
