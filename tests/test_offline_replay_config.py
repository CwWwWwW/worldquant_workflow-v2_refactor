from wq_workflow.config import load_config


def test_offline_replay_config_defaults_are_conservative():
    cfg = load_config()
    assert cfg.enable_offline_replay is False
    assert cfg.enable_counterfactual_evaluation is False
    assert cfg.offline_replay_auto_run is False
    assert cfg.offline_replay_mode == "advisory"
    assert cfg.offline_replay_min_observable_samples == 30
    assert cfg.offline_replay_baseline_policy == "legacy"
