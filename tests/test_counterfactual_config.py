from wq_workflow.config import load_config


def test_counterfactual_config_defaults():
    cfg=load_config()
    assert cfg.enable_counterfactual_evaluation is False
    assert cfg.counterfactual_auto_run is False
    assert cfg.counterfactual_mode=='advisory'
    assert cfg.counterfactual_min_evidence==30
    assert cfg.counterfactual_similarity_threshold==0.55
