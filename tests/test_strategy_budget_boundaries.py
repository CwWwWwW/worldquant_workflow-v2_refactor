from __future__ import annotations

from pathlib import Path


def test_strategy_budget_boundaries_no_takeover_imports():
    text = "\n".join(Path(p).read_text(encoding="utf-8") for p in [
        "wq_workflow/strategy/budget_schema.py",
        "wq_workflow/strategy/budget_policy.py",
        "wq_workflow/strategy/budget_allocator.py",
        "wq_workflow/strategy/budget_service.py",
    ])
    forbidden = ["playwright", ".page", "browser", "CandidatePool", "RewardService", "submit", "promotion.py", "rollback.py", "auto_apply_allowed=True"]
    assert not any(token in text for token in forbidden)
    assert "auto_apply_allowed=False" in text or '"auto_apply_allowed": False' in text
