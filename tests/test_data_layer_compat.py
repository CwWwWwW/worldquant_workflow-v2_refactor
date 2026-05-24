from __future__ import annotations

import sqlite3


def test_schema_and_repositories_on_temp_db(tmp_path):
    from wq_workflow.data.repositories import CandidateRepository, IterationRepository, MLRepository
    from wq_workflow.storage.schema import initialize_schema

    db = tmp_path / "workflow.db"
    conn = sqlite3.connect(db)
    try:
        initialize_schema(conn)
        candidate_repo = CandidateRepository(conn=conn)
        candidate_repo.save_candidate({"alpha_id": "a1", "expression": "rank(close)", "reward": 1.2})
        assert candidate_repo.get_candidate("a1")["alpha_id"] == "a1"
        assert candidate_repo.load_candidates(limit=5)
        assert candidate_repo.select_parent_candidates(limit=5)
        assert candidate_repo.update_candidate("a1", {"reward": 2.0}) is True

        iteration_repo = IterationRepository(conn=conn)
        iteration_repo.append_iteration({"alpha_id": "a1", "state": "done"})
        assert iteration_repo.load_recent_iterations(limit=5)

        ml_repo = MLRepository(conn=conn)
        assert ml_repo.insert_training_sample({"sample_id": "s1", "task_name": "sc", "features": {}, "label": {}})
        assert ml_repo.load_training_samples("sc", limit=5)
    finally:
        conn.close()
