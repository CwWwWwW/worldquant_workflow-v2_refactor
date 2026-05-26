from __future__ import annotations

from pathlib import Path


def test_legacy_bridge_python_boundaries():
    root = Path("wq_workflow/legacy_bridge")
    text = "\n".join(path.read_text(encoding="utf-8").lower() for path in root.glob("*.py"))
    for forbidden in [
        "playwright",
        "submit_backtest",
        "run_platform_backtest",
        "candidatepool(",
        "rewardengine(",
        "hard_decision_flags",
        "strategy budget apply",
        "promote_strategy",
        "rollback_strategy",
        "train_model",
        "sqlite3",
        "create table",
        "drop table",
        "alter table",
    ]:
        assert forbidden not in text
