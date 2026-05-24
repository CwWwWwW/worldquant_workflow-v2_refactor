import sqlite3

from wq_workflow.learning.ml.availability import require_joblib
from wq_workflow.learning.ml.feature_schema import FeatureSchema, SimpleFeatureSchema
from wq_workflow.learning.ml.model_registry import ModelRegistry
from wq_workflow.learning.ml.safe_model_io import load_model, save_model
from wq_workflow.storage.schema import initialize_schema


class DummyModel:
    def predict(self, X):
        return [0.1 for _ in X]


def test_feature_schema_transform_one():
    schema = SimpleFeatureSchema(feature_names=["a", "b"], defaults={"b": 2.0})
    assert schema.transform_one({"a": "1.5"}) == [1.5, 2.0]
    assert SimpleFeatureSchema.from_json(schema.to_json()).feature_names == ["a", "b"]


def test_safe_model_io_and_registry(tmp_path):
    db_path = tmp_path / "workflow.db"
    conn = sqlite3.connect(db_path)
    initialize_schema(conn)
    conn.close()

    registry = ModelRegistry(root=tmp_path, db_path=db_path)
    assert registry.load_active_model("sc") is None

    if require_joblib() is None:
        assert save_model(DummyModel(), tmp_path / "m.joblib") is False
        return

    model_path = tmp_path / "m.joblib"
    assert save_model(DummyModel(), model_path) is True
    assert isinstance(load_model(model_path), DummyModel)

    schema = SimpleFeatureSchema(feature_names=["x"])
    payload = registry.save_and_activate("sc", DummyModel(), schema, model_version="v1", train_sample_count=3)
    assert payload is not None
    active = registry.load_active_model("sc")
    assert active is not None
    assert active["model_version"] == "v1"
    assert isinstance(active["feature_schema"], FeatureSchema)
    assert registry.get_active_metadata("sc") is not None
    assert len(registry.list_models("sc")) >= 1
    assert registry.rollback("sc", "v1") is True

    (tmp_path / "runtime" / "models" / "sc" / "active_model.json").write_text("not json", encoding="utf-8")
    assert registry.load_active_model("sc") is None
    assert registry.deactivate_all("sc") is True
