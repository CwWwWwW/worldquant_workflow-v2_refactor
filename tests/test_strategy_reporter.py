import json

from wq_workflow.strategy.reporter import StrategyReporter
from wq_workflow.strategy.schema import StrategyScore, StrategyScoreboard


def test_strategy_reporter_atomic_and_corrupt_recovery(tmp_path):
    path = tmp_path / "strategy_scoreboard.json"
    path.write_text("{bad", encoding="utf-8")
    board = StrategyScoreboard(scoreboard_id="b1", scores=[StrategyScore(strategy_id="legacy_baseline", strategy_type="legacy_baseline", recommendation="keep_baseline")], evidence_summary={"legacy": {}})
    result = StrategyReporter(status_path=path).update(board)
    assert result["ok"] is True
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["strategies"][0]["strategy_id"] == "legacy_baseline"
    assert list(tmp_path.glob("*.bak")) or list(tmp_path.glob("*.corrupt.*.bak"))


def test_strategy_reporter_write_failure_not_fatal(tmp_path):
    reporter = StrategyReporter(status_path=tmp_path / "status.json")
    reporter._write_atomic = lambda payload: (_ for _ in ()).throw(OSError("boom"))
    result = reporter.update(StrategyScoreboard(scoreboard_id="b1"))
    assert result["ok"] is False
