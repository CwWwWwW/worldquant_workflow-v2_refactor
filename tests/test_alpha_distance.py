from wq_workflow.alpha.representation.distance import (
    combined_expression_similarity,
    field_similarity,
    operator_similarity,
    subtree_similarity,
)
from wq_workflow.alpha.representation.features import build_alpha_representation


def test_same_expression_similarity_close_to_one():
    a = build_alpha_representation("rank(close)")
    b = build_alpha_representation("rank(close)")
    assert combined_expression_similarity(a, b) >= 0.95


def test_different_expression_similarity_lower():
    a = build_alpha_representation("rank(close)")
    b = build_alpha_representation("group_neutralize(ts_rank(volume, 60), industry)")
    assert combined_expression_similarity(a, b) < 0.8


def test_component_similarities_and_missing_inputs_do_not_crash():
    a = build_alpha_representation("rank(close)")
    b = build_alpha_representation("rank(volume)")
    assert operator_similarity(a, b) == 1.0
    assert field_similarity(a, b) == 0.0
    assert 0.0 <= subtree_similarity(a, b) <= 1.0
    assert combined_expression_similarity(None, b) >= 0.0
