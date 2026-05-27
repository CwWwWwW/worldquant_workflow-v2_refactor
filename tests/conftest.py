from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator

import pytest


_ENV_PREFIXES_TO_ISOLATE = (
    "WORLDQUANT_",
    "WQ_",
    "DEEPSEEK_",
    "ENABLE_",
    "PLATFORM_SC_",
    "V2_",
    "INSIGHT_",
    "MAX_AST_",
    "MAX_EXPR_",
    "MAX_NESTED_",
    "MAX_OPERATOR_",
    "RUN_WQ_",
)

_ENV_NAMES_TO_ISOLATE = {
    "WQ_ALPHA_URL",
}


def _reset_storage_manager() -> None:
    try:
        import wq_workflow.storage.manager as manager_module

        manager = getattr(manager_module, "_MANAGER", None)
        if manager is not None:
            try:
                manager.close()
            except Exception:
                pass
        manager_module._MANAGER = None
    except Exception:
        pass


@pytest.fixture(autouse=True)
def isolate_local_config_and_storage(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    """Keep tests independent from private local config/runtime state.

    Production code still reads the repository-level config.json by default. Tests
    patch that path to a per-test missing file so default configuration assertions
    are not polluted by a developer's private local config.json.
    """

    for name in list(os.environ):
        if name in _ENV_NAMES_TO_ISOLATE or any(name.startswith(prefix) for prefix in _ENV_PREFIXES_TO_ISOLATE):
            monkeypatch.delenv(name, raising=False)

    isolated_config = tmp_path / "config.json"
    isolated_db = tmp_path / "runtime" / "db" / "workflow.db"

    import wq_workflow.config as config_module
    import wq_workflow.paths as paths_module

    monkeypatch.setattr(config_module, "CONFIG_FILE", isolated_config)
    monkeypatch.setattr(paths_module, "CONFIG_FILE", isolated_config)
    monkeypatch.setenv("WQ_STORAGE_DB_PATH", str(isolated_db))

    _reset_storage_manager()
    try:
        yield
    finally:
        _reset_storage_manager()
