from wq_workflow.alpha.representation.features import build_alpha_representation
from wq_workflow.alpha.representation.fingerprint import behavior_fingerprint, expression_fingerprint, subtree_fingerprints


def test_expression_fingerprint_stable():
    a = build_alpha_representation("ts_rank(close, 20)")
    b = build_alpha_representation(" ts_rank( close, 20 ) ")
    assert expression_fingerprint(a) == expression_fingerprint(b)
    assert a.expression_hash == b.expression_hash


def test_empty_expression_fingerprint_stable():
    a = build_alpha_representation("")
    b = build_alpha_representation("")
    assert a.expression_hash == b.expression_hash
    assert a.behavior_fingerprint == b.behavior_fingerprint


def test_subtree_and_behavior_fingerprints_stable():
    rep = build_alpha_representation("group_neutralize(rank(close), industry)")
    assert subtree_fingerprints(rep.ast)
    assert rep.subtree_fingerprints
    assert behavior_fingerprint(rep) == behavior_fingerprint(rep)
