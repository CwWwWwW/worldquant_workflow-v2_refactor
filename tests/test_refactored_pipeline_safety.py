import asyncio

from wq_workflow.app.config_guard import apply_config_safety_gate
from wq_workflow.models import WorkflowConfig
from wq_workflow.workflow.pipeline import WorkflowPipeline, has_observe_only_critical_steps
from wq_workflow.workflow.steps import DEFAULT_STEP_CLASSES


class Ctx:
    def __init__(self):
        self.config = WorkflowConfig()
        self.logger = None
        self.runtime_status = {}
        self.strategy_services = {}
        self.learning_services = {}
        self.data_services = {}
        self.monitoring_services = {}


def test_critical_observe_only_steps_are_detected():
    pipeline = WorkflowPipeline(Ctx())
    assert has_observe_only_critical_steps(pipeline.steps) is True


def test_config_guard_disables_unsafe_refactored_pipeline():
    cfg = WorkflowConfig(enable_refactored_pipeline=True, allow_observe_only_pipeline=False)
    result = apply_config_safety_gate(cfg, model_registry=None, step_classes=DEFAULT_STEP_CLASSES)
    assert result["effective_config"].enable_refactored_pipeline is False
    assert cfg.enable_refactored_pipeline is True
    assert "enable_refactored_pipeline" in result["disabled_flags"]


def test_shadow_mode_is_not_official_result_source():
    cfg = WorkflowConfig(enable_refactored_pipeline=True, enable_refactored_pipeline_shadow=True)
    result = apply_config_safety_gate(cfg, model_registry=None)
    assert result["effective_config"].enable_refactored_pipeline is False
    assert any("observe-only" in warning for warning in result["warnings"])


def test_bootstrap_falls_back_to_legacy_when_refactored_pipeline_unsafe(monkeypatch):
    import wq_workflow.app.bootstrap as bootstrap

    ctx = Ctx()
    ctx.config = WorkflowConfig(enable_refactored_pipeline=True, allow_observe_only_pipeline=False)
    called = {"legacy": False}

    async def legacy_adapter(ctx_arg, argv=None):
        called["legacy"] = True
        return 7

    ctx.legacy_adapters = {"orchestrator": legacy_adapter}

    def fake_build(config=None):
        return ctx

    monkeypatch.setattr(bootstrap, "build_app_context", fake_build)
    assert asyncio.run(bootstrap.run_async([])) == 7
    assert called["legacy"] is True
    assert ctx.runtime_status["official_result_source"] == "legacy"


def test_allow_observe_only_pipeline_is_marked_unsafe(monkeypatch):
    cfg = WorkflowConfig(enable_refactored_pipeline=True, allow_observe_only_pipeline=True)
    result = apply_config_safety_gate(cfg, model_registry=None)
    assert result["effective_config"].enable_refactored_pipeline is True
    assert any("UNSAFE" in warning for warning in result["warnings"])
