import json

from wq_workflow.strategy.portfolio_reporter import StrategyPortfolioReporter
from wq_workflow.strategy.portfolio_schema import StrategyPortfolio, StrategyState, StrategyTransition


def test_strategy_portfolio_reporter_atomic_and_corrupt_recovery(tmp_path):
    path = tmp_path / "strategy_portfolio_report.json"
    path.write_text("{bad", encoding="utf-8")
    portfolio = StrategyPortfolio(portfolio_id="p1", states=[StrategyState(strategy_id="legacy_baseline", recommended_state="champion")], transitions=[StrategyTransition(transition_id="t1", strategy_id="legacy_baseline", to_state="champion")])
    result = StrategyPortfolioReporter(status_path=path).update(portfolio)
    assert result["ok"] is True
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["states"][0]["strategy_id"] == "legacy_baseline"
    assert payload["transitions"][0]["auto_apply_allowed"] is False
    assert list(tmp_path.glob("*.bak")) or list(tmp_path.glob("*.corrupt.*.bak"))


def test_strategy_portfolio_reporter_write_failure_not_fatal(tmp_path):
    reporter = StrategyPortfolioReporter(status_path=tmp_path / "status.json")
    reporter._write_atomic = lambda payload: (_ for _ in ()).throw(OSError("boom"))
    result = reporter.update(StrategyPortfolio(portfolio_id="p1"))
    assert result["ok"] is False
