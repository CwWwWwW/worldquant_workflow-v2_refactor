from __future__ import annotations

from pathlib import Path


def test_observability_boundaries_static():
    text = "\n".join(path.read_text(encoding="utf-8") for path in Path("wq_workflow/observability").glob("*.py"))
    forbidden = ["playwright", "CandidatePool", "auto_apply_allowed = True"]
    for item in forbidden:
        assert item not in text
    assert "metrics_only" in text
    assert "AlertRuleEngine" in text and "DriftDetector" in text and "HealthDiagnosisService" in text
