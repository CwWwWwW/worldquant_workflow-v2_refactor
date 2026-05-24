from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_readme_warns_refactored_pipeline_is_shadow_not_production_default():
    text = (ROOT / "README.md").read_text(encoding="utf-8", errors="ignore").lower()
    assert "refactored pipeline status" in text
    assert "shadow" in text
    assert "not the production official default" in text
    assert "legacy official workflow" in text


def test_config_example_refactored_pipeline_defaults_are_safe():
    data = json.loads((ROOT / "config.example.json").read_text(encoding="utf-8-sig"))

    assert data["enable_refactored_pipeline"] is False
    assert data["enable_refactored_pipeline_shadow"] is True
    assert data["allow_observe_only_pipeline"] is False

    note = str(data.get("refactored_pipeline_note", "")).lower()
    assert "shadow" in note
    assert "production" in note
