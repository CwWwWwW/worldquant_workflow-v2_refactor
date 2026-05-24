import json
import sqlite3

import wq_workflow.learning.ml.model_registry as registry_module
from wq_workflow.learning.ml.feature_schema import SimpleFeatureSchema
from wq_workflow.learning.ml.model_registry import ModelRegistry
from wq_workflow.storage.schema import initialize_schema


def _db(tmp_path):
    db = tmp_path / "workflow.db"
    conn = sqlite3.connect(db)
    initialize_schema(conn)
    conn.close()
    return db


def _insert_model(conn, task, version, model_path, active=1):
    conn.execute(
        """
        INSERT OR REPLACE INTO ml_model_registry
        (model_id, task_name, model_version, model_path, feature_schema_json, train_sample_count,
         validation_metric_json, is_active, created_at, raw_payload)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"{task}:{version}",
            task,
            version,
            str(model_path),
            "{}",
            1,
            "{}",
            active,
            version,
            "{}",
        ),
    )
    conn.commit()


def test_active_pointer_to_missing_file_fails_consistency(tmp_path):
    db = _db(tmp_path)
    reg = ModelRegistry(root=tmp_path, db_path=db)
    active = tmp_path / "runtime" / "models" / "sc" / "active_model.json"
    active.parent.mkdir(parents=True)
    active.write_text(json.dumps({"task_name": "sc", "model_version": "v1", "model_path": str(tmp_path / "missing.joblib")}), encoding="utf-8")
    conn = sqlite3.connect(db)
    _insert_model(conn, "sc", "v1", tmp_path / "missing.joblib", active=1)
    conn.close()
    result = reg.check_registry_consistency("sc")
    assert result["ok"] is False
    assert any(issue["issue"] in {"broken_active_pointer", "missing_model_file"} for issue in result["issues"])


def test_multiple_active_models_are_repaired_to_at_most_one(tmp_path):
    db = _db(tmp_path)
    reg = ModelRegistry(root=tmp_path, db_path=db)
    conn = sqlite3.connect(db)
    _insert_model(conn, "sc", "v1", tmp_path / "m1.joblib", active=1)
    _insert_model(conn, "sc", "v2", tmp_path / "m2.joblib", active=1)
    conn.close()
    assert any(issue["issue"] == "multiple_active" for issue in reg.check_registry_consistency("sc")["issues"])
    reg.repair_registry("sc")
    conn = sqlite3.connect(db)
    count = conn.execute("SELECT COUNT(*) FROM ml_model_registry WHERE task_name='sc' AND is_active=1").fetchone()[0]
    conn.close()
    assert count <= 1


def test_load_active_model_returns_none_when_model_file_missing(tmp_path):
    db = _db(tmp_path)
    reg = ModelRegistry(root=tmp_path, db_path=db)
    active = tmp_path / "runtime" / "models" / "sc" / "active_model.json"
    active.parent.mkdir(parents=True)
    missing = tmp_path / "missing.joblib"
    active.write_text(json.dumps({"task_name": "sc", "model_version": "v1", "model_path": str(missing)}), encoding="utf-8")
    conn = sqlite3.connect(db)
    _insert_model(conn, "sc", "v1", missing, active=1)
    conn.close()
    assert reg.load_active_model("sc") is None


def test_save_and_activate_does_not_return_ok_when_db_write_fails(monkeypatch, tmp_path):
    bad_db_path = tmp_path / "db_as_directory"
    bad_db_path.mkdir()
    reg = ModelRegistry(model_root=tmp_path / "models", db_path=bad_db_path)

    monkeypatch.setattr(registry_module, "require_joblib", lambda: object())

    def fake_save_model(model, path, logger=None):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("model", encoding="utf-8")
        return True

    monkeypatch.setattr(registry_module, "save_model", fake_save_model)
    result = reg.save_and_activate("sc", {"model": True}, SimpleFeatureSchema(["x"]), model_version="v1")
    assert result is not None
    assert result["ok"] is False
    assert result["registry_written"] is False


def test_repair_broken_active_pointer_does_not_break_main_flow(tmp_path):
    db = _db(tmp_path)
    reg = ModelRegistry(root=tmp_path, db_path=db)
    active = tmp_path / "runtime" / "models" / "sc" / "active_model.json"
    active.parent.mkdir(parents=True)
    active.write_text("{not json", encoding="utf-8")
    assert reg.load_active_model("sc") is None
    result = reg.repair_registry("sc")
    assert "ok" in result
