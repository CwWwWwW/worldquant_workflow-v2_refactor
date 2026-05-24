import pytest

from wq_workflow.alpha.representation.errors import AlphaParseError
from wq_workflow.alpha.representation.features import build_alpha_representation
from wq_workflow.alpha.representation.parser import parse_expression


def test_parse_simple_ts_rank():
    ast = parse_expression("ts_rank(close, 20)")
    assert ast is not None
    assert ast.node_type == "operator"
    assert ast.value == "ts_rank"
    assert ast.operators() == ["ts_rank"]
    assert ast.fields() == ["close"]
    assert ast.numbers() == [20.0]


def test_parse_nested_expression():
    ast = parse_expression("rank(ts_delta(close, 5))")
    assert ast is not None
    assert ast.operators() == ["rank", "ts_delta"]
    assert ast.fields() == ["close"]
    assert ast.numbers() == [5.0]


def test_parse_group_neutralize():
    ast = parse_expression("group_neutralize(rank(close), industry)")
    assert ast is not None
    assert ast.operators() == ["group_neutralize", "rank"]
    assert ast.fields() == ["close", "industry"]


def test_parse_failure_fallback():
    with pytest.raises(AlphaParseError):
        parse_expression("rank(close")
    rep = build_alpha_representation("rank(close")
    assert rep.parse_status == "failed"
    assert rep.features["operator_count"] == 0
