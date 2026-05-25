from wq_workflow.strategy.schema import StrategyEvidence, StrategyProfile, StrategyScore, StrategyScoreboard, StrategySignal


def _roundtrip(obj, cls):
    data = obj.to_dict()
    assert isinstance(data, dict)
    assert cls.from_dict(data).to_dict()[next(iter(data.keys()))] == data[next(iter(data.keys()))]
    return data


def test_strategy_schema_roundtrip_json_safe():
    profile = StrategyProfile(strategy_id="legacy_baseline", strategy_type="legacy_baseline", raw_payload={"x": object()})
    evidence = StrategyEvidence(evidence_id="e1", strategy_id="legacy_baseline", sample_count=3, risk_flags=["a"])
    signal = StrategySignal(signal_id="s1", strategy_id="legacy_baseline", value=True)
    score = StrategyScore(strategy_id="legacy_baseline", strategy_type="legacy_baseline", total_score=2.0)
    board = StrategyScoreboard(scoreboard_id="b1", profiles=[profile], scores=[score], signals=[signal], evidence_summary={"x": 1})
    assert _roundtrip(profile, StrategyProfile)["created_at"].endswith("+00:00")
    _roundtrip(evidence, StrategyEvidence)
    _roundtrip(signal, StrategySignal)
    assert StrategyScore.from_dict(score.to_dict()).total_score == 1.0
    assert StrategyScoreboard.from_dict(board.to_dict()).profiles[0].strategy_id == "legacy_baseline"
