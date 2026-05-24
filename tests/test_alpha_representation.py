from wq_workflow.alpha.representation.features import build_alpha_representation


def test_alpha_representation_extracts_basic_features():
    rep = build_alpha_representation("ts_rank(close, 20)")
    assert "ts_rank" in rep.operator_sequence
    assert "close" in rep.field_sequence
    assert rep.features["operator_count"] >= 1
    assert rep.features["field_count"] >= 1
    assert rep.numeric_params == [20.0]


def test_alpha_representation_empty_expression_no_crash():
    rep = build_alpha_representation("")
    assert rep.raw_expression == ""
    assert isinstance(rep.features, dict)
