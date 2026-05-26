from __future__ import annotations

from pathlib import Path

from wq_workflow.observability.alert_schema import HealthDiagnosis


def test_observability_alert_boundaries_static():
    files = [path for path in Path("wq_workflow/observability").glob("*.py") if path.name not in {"source_adapters.py"}]
    text = "\n".join(path.read_text(encoding="utf-8") for path in files)
    for item in ["playwright", "CandidatePool", "external alert", "auto_action_allowed = True"]:
        assert item not in text
    assert "apply_budget" not in text
    assert HealthDiagnosis(auto_action_allowed=True).to_dict()["auto_action_allowed"] is False
