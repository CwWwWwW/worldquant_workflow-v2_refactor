import sqlite3

from wq_workflow.storage.schema import initialize_schema
from wq_workflow.data.repositories import MLRepository
from wq_workflow.learning.ml.schema import MLTrainingSample


def test_ml_tables_created_and_schema_is_idempotent(tmp_path):
    db = tmp_path / "workflow.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE legacy_table (id TEXT PRIMARY KEY)")
    conn.execute("INSERT INTO legacy_table VALUES ('keep')")
    conn.commit()

    initialize_schema(conn)
    initialize_schema(conn)

    tables = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    assert {"ml_model_registry", "ml_prediction_audit", "ml_training_samples", "evolution_meta"}.issubset(tables)
    assert conn.execute("SELECT id FROM legacy_table").fetchone()[0] == "keep"
    conn.close()


def test_ml_repository_accepts_training_sample_dataclass(tmp_path):
    db = tmp_path / "workflow.db"
    conn = sqlite3.connect(db)
    initialize_schema(conn)
    conn.close()

    repo = MLRepository(db_path=db)
    sample = MLTrainingSample(sample_id="s1", task_name="sc", alpha_id="a1", features={"x": 1}, label={"y": 2})
    assert repo.insert_training_sample(sample) is True
    assert repo.load_training_samples("sc")[0]["features"] == {"x": 1}
    assert repo.list_model_registry("sc") == []
