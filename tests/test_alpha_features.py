from wq_workflow.alpha.representation.features import build_alpha_representation


def test_build_alpha_representation_outputs_features():
    rep = build_alpha_representation("ts_rank(close, 20)")
    assert rep.parse_status == "ok"
    assert rep.root_operator == "ts_rank"
    assert rep.features["expression_length"] > 0
    assert rep.features["operator_count"] == 1
    assert rep.features["field_count"] == 1
    assert rep.features["ast_depth"] >= 1
    assert rep.features["has_ts_operator"] is True
    assert isinstance(rep.feature_vector, list)


def test_group_features_and_summary():
    rep = build_alpha_representation("group_neutralize(rank(close), industry)")
    assert rep.features["has_group_operator"] is True
    assert rep.summary()["expression_hash"] == rep.expression_hash
    assert rep.summary()["behavior_fingerprint"] == rep.behavior_fingerprint


def test_failure_representation_is_fail_soft():
    rep = build_alpha_representation("rank(close")
    assert rep.parse_status == "failed"
    assert rep.parse_error
    assert isinstance(rep.features, dict)
