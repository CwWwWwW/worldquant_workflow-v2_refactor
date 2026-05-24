from wq_workflow.learning.ml.evaluation import validation_gate
from wq_workflow.learning.ml.feature_schema import SimpleFeatureSchema
from wq_workflow.learning.ml.model_registry import ModelRegistry
from wq_workflow.models import WorkflowConfig


class DummyModel:
    def predict(self, X):
        return [0.1 for _ in X]


def test_validation_gate_and_registry_rollback(tmp_path):
    cfg = WorkflowConfig(sc_learning_min_samples=3, sc_model_max_mae=0.1)
    assert validation_gate("sc", {"sample_count": 2, "mae": 0.01}, cfg)["passed"] is False
    assert validation_gate("sc", {"sample_count": 3, "mae": 0.5}, cfg)["passed"] is False
    assert validation_gate("sc", {"sample_count": 3, "mae": 0.01}, cfg)["passed"] is True
    reg = ModelRegistry(root=tmp_path)
    meta = reg.save_model_version("sc", DummyModel(), SimpleFeatureSchema(["x"]), model_version="v1", train_sample_count=3, evaluation={"metrics": {"sample_count":3,"mae":0.01}, "validation_gate": {"passed": True}})
    if meta is None:
        return
    assert reg.activate_model("sc", "v1") is True
    assert reg.rollback_to_version("sc", "v1") is True
