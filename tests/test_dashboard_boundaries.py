from __future__ import annotations

from pathlib import Path


def test_dashboard_package_does_not_import_or_call_forbidden_actions():
    root = Path("wq_workflow/dashboard")
    text = "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*.py"))
    forbidden = [
        "playwright",
        "browser",
        "page.",
        "CandidatePool",
        "reward_engine",
        "collect_metrics(",
        "run_diagnostics(",
        "generate_explanations(",
        "subprocess",
        "promote_strategy",
        "rollback_strategy",
        "allocate(",
        "INSERT ",
        "UPDATE ",
        "DELETE ",
        "DROP ",
        "ALTER ",
        "CREATE TABLE",
    ]
    lowered = text.lower()
    for needle in forbidden:
        assert needle.lower() not in lowered
