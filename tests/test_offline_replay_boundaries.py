from pathlib import Path


def test_offline_replay_layer_boundaries_are_advisory():
    text = "\n".join(path.read_text(encoding="utf-8") for path in Path("wq_workflow/offline").glob("*.py"))
    lower = text.lower()
    assert "playwright" not in lower
    assert ".goto(" not in text
    assert "CandidatePool" not in text
    assert "run_platform_backtest" not in text
    assert "enable_offline_replay = True" not in text
    assert "enable_counterfactual_evaluation = True" not in text
    assert "force_enable_unsafe_ml_decisions" not in Path("wq_workflow/offline/replay_engine.py").read_text(encoding="utf-8")
