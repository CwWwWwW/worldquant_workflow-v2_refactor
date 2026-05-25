from pathlib import Path


def test_offline_layer_boundaries_no_browser_takeover():
    offline_files = list(Path("wq_workflow/offline").glob("*.py"))
    text = "\n".join(path.read_text(encoding="utf-8") for path in offline_files)
    assert "playwright" not in text.lower()
    assert ".goto(" not in text
    assert "CandidatePool" not in text
    assert "run_platform_backtest" not in text
    assert "enable_offline_replay = True" not in text
    assert "enable_counterfactual_evaluation = True" not in text
