from pathlib import Path


def test_strategy_boundaries_no_platform_takeover_imports():
    root = Path("wq_workflow/strategy")
    phase6_files = ["schema.py", "registry.py", "evidence_loader.py", "scorer.py", "scoreboard.py", "repository.py", "reporter.py", "service.py"]
    text = "\n".join((root / name).read_text(encoding="utf-8") for name in phase6_files)
    forbidden = ["playwright", "browser", "page.", "CandidatePool", "reward_engine", "submit", "promote_if_eligible", "rollback_to_legacy", "generate_budget_plan"]
    lowered = text.lower()
    for token in forbidden:
        assert token.lower() not in lowered
    assert "estimated_not_observed" in text
