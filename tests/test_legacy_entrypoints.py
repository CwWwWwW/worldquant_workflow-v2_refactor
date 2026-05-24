from __future__ import annotations

import importlib


def test_legacy_entrypoint_imports_do_not_break():
    for name in [
        "worldquant_auto_workflow",
        "wq_workflow",
        "wq_workflow.__main__",
        "wq_workflow.cli",
        "wq_workflow.config",
        "wq_workflow.orchestrator",
        "wq_workflow.simulate",
        "wq_workflow.platform_sc",
        "wq_workflow.candidate_pool",
        "wq_workflow.reward_engine",
        "wq_workflow.storage.schema",
    ]:
        assert importlib.import_module(name)
