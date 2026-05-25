from wq_workflow.strategy.repository import StrategyRepository
from wq_workflow.strategy.schema import StrategyEvidence, StrategyProfile, StrategyScore, StrategyScoreboard, StrategySignal


def test_strategy_repository_crud_idempotent(tmp_path):
    repo = StrategyRepository(db_path=tmp_path / "workflow.db")
    assert repo.initialize()["ok"] is True
    profile = StrategyProfile(strategy_id="legacy_baseline", strategy_type="legacy_baseline")
    assert repo.save_profile(profile) and repo.save_profile(profile)
    assert repo.get_profile("legacy_baseline").strategy_id == "legacy_baseline"
    assert repo.list_profiles("legacy_baseline")
    evidence = StrategyEvidence(evidence_id="e1", strategy_id="legacy_baseline", sample_count=1)
    assert repo.save_evidence(evidence)
    assert repo.list_evidence("legacy_baseline")[0].evidence_id == "e1"
    signal = StrategySignal(signal_id="s1", strategy_id="legacy_baseline", value=1.0)
    assert repo.save_signal(signal)
    assert repo.list_signals("legacy_baseline")[0].signal_id == "s1"
    score = StrategyScore(strategy_id="legacy_baseline", strategy_type="legacy_baseline", total_score=0.5)
    assert repo.save_score(score)
    assert repo.get_score("legacy_baseline").total_score == 0.5
    board = StrategyScoreboard(scoreboard_id="b1", profiles=[profile], scores=[score], signals=[signal])
    assert repo.save_scoreboard(board)
    assert repo.get_latest_scoreboard().scoreboard_id == "b1"
    assert repo.list_scoreboards()[0].scoreboard_id == "b1"
