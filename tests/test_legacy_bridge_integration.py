from __future__ import annotations

from types import SimpleNamespace

from wq_workflow.legacy_bridge.integration import build_legacy_observer, observer_enabled, safe_observe


def test_build_observer_enabled_disabled(tmp_path):
    enabled = SimpleNamespace(enable_legacy_iteration_observer=True, legacy_runtime_state_path="runtime/status/runtime_state.json")
    disabled = SimpleNamespace(enable_legacy_iteration_observer=False)
    assert observer_enabled(enabled) is True
    assert build_legacy_observer(disabled, root=tmp_path) is None
    assert build_legacy_observer(enabled, root=tmp_path) is not None


def test_safe_observe_none_missing_exception_and_return_value():
    assert safe_observe(None, "missing") is None

    class Bad:
        def boom(self, **kwargs):
            raise RuntimeError("boom")

    assert safe_observe(Bad(), "missing") is None
    assert safe_observe(Bad(), "boom") is None
