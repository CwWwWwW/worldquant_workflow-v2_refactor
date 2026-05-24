from wq_workflow.learning.ml.feature_schema import FeatureSchema, SimpleFeatureSchema


def test_feature_schema_transform_and_round_trip():
    schema = FeatureSchema(
        schema_version="v1",
        feature_names=["a", "missing", "flag", "none", "nan", "inf"],
        numeric_features=["a", "missing", "nan", "inf"],
        boolean_features=["flag"],
        metadata={"source": "test"},
    )

    row = schema.transform_one({"a": "1.5", "flag": True, "none": None, "nan": float("nan"), "inf": float("inf")})
    assert row == [1.5, 0.0, 1.0, 0.0, 0.0, 0.0]
    assert schema.transform_many([{"a": 2}, {"flag": False}]) == [
        [2.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    ]

    restored = FeatureSchema.from_dict(schema.to_dict())
    assert restored.to_dict() == schema.to_dict()


def test_simple_feature_schema_compatibility():
    schema = SimpleFeatureSchema(feature_names=["x", "flag"], defaults={"x": 3.0})
    assert schema.transform_one({"flag": True}) == [3.0, 1.0]
    assert SimpleFeatureSchema.from_dict(schema.to_dict()).feature_names == ["x", "flag"]
