import json

from wq_workflow.models import WorkflowConfig


def test_workflow_config_ml_defaults_are_conservative():
    cfg = WorkflowConfig()
    assert cfg.enable_sc_model_training is True
    assert cfg.enable_parent_model_training is True
    assert cfg.enable_policy_model_training is True
    assert cfg.enable_simulator_model_training is True
    assert cfg.enable_sc_model_fallback is False
    assert cfg.enable_parent_model_decision is False
    assert cfg.enable_policy_model_decision is False
    assert cfg.enable_simulator_model_skip is False
    assert cfg.ml_allow_sklearn is True
    assert cfg.ml_allow_no_sklearn_fallback is True
    assert cfg.ml_model_root == "runtime/models"


def test_old_config_without_ml_fields_loads(monkeypatch, tmp_path):
    import wq_workflow.config as config_mod

    old_config = tmp_path / "config.json"
    old_config.write_text(json.dumps({"email": "old@example.com", "password": "x"}), encoding="utf-8")
    monkeypatch.setattr(config_mod, "CONFIG_FILE", old_config)

    cfg = config_mod.load_config()
    assert cfg.email == "old@example.com"
    assert cfg.ml_model_root == "runtime/models"
    assert cfg.enable_parent_model_decision is False
    assert cfg.enable_policy_model_decision is False
    assert cfg.enable_simulator_model_skip is False
