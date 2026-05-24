from wq_workflow.learning.ml.availability import require_numpy
from wq_workflow.learning.ml.feature_schema import FeatureSchema
from wq_workflow.learning.ml.training_utils import (
    build_feature_schema,
    build_xy_from_samples,
    has_enough_samples,
    new_model_version,
)


def test_training_utils_build_schema_and_sample_count():
    samples = [
        {"features": {"b": True, "a": 1.0, "text": "ignored"}, "label": {"y": 1}},
        {"features": {"a": 2, "c": None}, "label": {"y": 2}},
    ]
    schema = build_feature_schema(samples)
    assert schema.feature_names == ["a", "b"]
    assert has_enough_samples(samples, 2) is True
    assert has_enough_samples(samples, 3) is False
    assert new_model_version("sc").startswith("sc_v")


def test_build_xy_from_samples_skips_missing_label_and_cleans_values():
    samples = [
        {"features": {"x": 1, "bad": float("nan"), "cat": "a"}, "label": {"target": 1}},
        {"features": {"x": 2}, "label": {}},
        {"features": {"x": float("inf")}, "label": {"target": float("nan")}},
    ]
    x, y, schema = build_xy_from_samples(samples, "target")
    if require_numpy() is None:
        assert x is None and y is None and schema is None
        return
    assert isinstance(schema, FeatureSchema)
    assert len(y) == 2
    assert schema.feature_names
    assert not bool((x != x).any())
    assert not bool((y != y).any())
