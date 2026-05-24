from types import SimpleNamespace

from wq_workflow.app.bootstrap import build_app_context
from wq_workflow.models import WorkflowConfig
from wq_workflow.workflow.pipeline import WorkflowPipeline


def test_build_app_context_services_and_legacy_default():
    config = WorkflowConfig(enable_data_services=False)
    ctx = build_app_context(config=config)
    assert ctx.config.enable_refactored_pipeline is False
    assert ctx.service("platform", "sc_collector") is not None
    assert ctx.service("learning", "model_registry") is not None
    assert callable(ctx.legacy_adapters.get("orchestrator"))


def test_pipeline_shadow_run_skeleton():
    config = WorkflowConfig(enable_data_services=False)
    ctx = build_app_context(config=config)
    result = WorkflowPipeline(ctx).run_one_iteration()
    assert result.ok is True
    wf = result.data["workflow_context"]
    assert wf.strategy["strategy_id"] == "legacy_champion"
