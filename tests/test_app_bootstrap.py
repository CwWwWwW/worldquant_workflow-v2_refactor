from __future__ import annotations

from types import SimpleNamespace


def test_build_app_context_minimal_config():
    from wq_workflow.app.bootstrap import build_app_context

    cfg = SimpleNamespace(
        enable_data_services=False,
        enable_platform_services=True,
        enable_startup_healthcheck=False,
        enable_refactored_pipeline=False,
        allow_observe_only_pipeline=False,
        enable_alpha_representation=True,
        enable_drift_monitor=False,
        enable_auto_promotion=False,
        enable_auto_rollback=False,
        force_enable_unsafe_ml_decisions=False,
        enable_sc_model_fallback=False,
        enable_parent_model_decision=False,
        enable_policy_model_decision=False,
        enable_simulator_model_skip=False,
        ml_model_root="runtime/models",
        platform_sc_timeout_seconds=3,
    )
    ctx = build_app_context(config=cfg)
    assert getattr(ctx.config, "enable_refactored_pipeline", None) is False
    assert ctx.service("platform", "sc_collector") is not None
    assert ctx.service("evaluation", "reward") is not None
    assert ctx.legacy_adapters.get("orchestrator") is not None
