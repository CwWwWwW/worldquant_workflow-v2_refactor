from pathlib import Path

from wq_workflow.strategy.portfolio_schema import StrategyTransition


def test_strategy_portfolio_boundaries_no_takeover_imports():
    root = Path("wq_workflow/strategy")
    files = ["portfolio_schema.py", "transition_rules.py", "portfolio_policy.py", "portfolio_repository.py", "portfolio_reporter.py", "portfolio_service.py"]
    text = "\n".join((root / name).read_text(encoding="utf-8") for name in files)
    lowered = text.lower()
    forbidden = ["playwright", "browser", "page.", "candidatepool", "submit", "promote_if_eligible", "rollback_to_legacy", "budgetallocator"]
    for token in forbidden:
        assert token.lower() not in lowered
    assert StrategyTransition(auto_apply_allowed=True).to_dict()["auto_apply_allowed"] is False
