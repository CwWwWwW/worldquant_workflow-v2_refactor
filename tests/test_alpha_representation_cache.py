from wq_workflow.alpha.representation.cache import AlphaRepresentationCache
from wq_workflow.alpha.representation.features import build_alpha_representation


def test_build_or_get_hits_cache():
    cache = AlphaRepresentationCache(max_size=10)
    calls = {"count": 0}

    def builder(expr):
        calls["count"] += 1
        return build_alpha_representation(expr)

    first = cache.build_or_get("rank(close)", builder)
    second = cache.build_or_get(" rank( close ) ", builder)
    assert first is second
    assert calls["count"] == 1


def test_max_size_evicts_oldest():
    cache = AlphaRepresentationCache(max_size=1)
    cache.put("rank(close)", build_alpha_representation("rank(close)"))
    cache.put("rank(volume)", build_alpha_representation("rank(volume)"))
    assert cache.get("rank(close)") is None
    assert cache.get("rank(volume)") is not None


def test_cache_failure_falls_back_to_builder():
    class BadCache(AlphaRepresentationCache):
        def get(self, expression):
            raise RuntimeError("boom")

    rep = BadCache().build_or_get("rank(close)", build_alpha_representation)
    assert rep.parse_status == "ok"
