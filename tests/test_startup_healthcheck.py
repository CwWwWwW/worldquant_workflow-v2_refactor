import json
import sqlite3
from pathlib import Path

import wq_workflow.learning.ml.availability as availability
from wq_workflow.app.healthcheck import run_startup_healthcheck
from wq_workflow.learning.ml.model_registry import ModelRegistry
from wq_workflow.models import WorkflowConfig


def test_healthcheck_creates_missing_ml_tables(tmp_path):
    cfg = WorkflowConfig(storage_db_path=str(tmp_path / "workflow.db"), healthcheck_audit_path=str(tmp_path / "audit.jsonl"))
    result = run_startup_healthcheck(cfg, root=tmp_path)
    assert result["ok"] is True
    conn = sqlite3.connect(tmp_path / "workflow.db")
    assert conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ml_model_registry'").fetchone()
    conn.close()


def test_healthcheck_refactored_pipeline_misconfig_suggests_legacy(tmp_path):
    cfg = WorkflowConfig(
        storage_db_path=str(tmp_path / "workflow.db"),
        enable_refactored_pipeline=True,
        healthcheck_audit_path=str(tmp_path / "audit.jsonl"),
    )
    result = run_startup_healthcheck(cfg, root=tmp_path)
    assert result["mode"] in {"safe_legacy", "degraded_ml_disabled"}
    assert any("runtime_force_legacy" in item for item in result["auto_fixes"])


def test_healthcheck_detects_broken_active_model(tmp_path):
    db = tmp_path / "workflow.db"
    cfg = WorkflowConfig(storage_db_path=str(db), healthcheck_audit_path=str(tmp_path / "audit.jsonl"))
    reg = ModelRegistry(root=tmp_path, db_path=db)
    active = tmp_path / "runtime" / "models" / "sc" / "active_model.json"
    active.parent.mkdir(parents=True)
    active.write_text(json.dumps({"task_name": "sc", "model_version": "v1", "model_path": str(tmp_path / "missing.joblib")}), encoding="utf-8")
    result = run_startup_healthcheck(cfg, model_registry=reg, root=tmp_path)
    assert any("active_model_registry_inconsistent" in warning for warning in result["warnings"])


def test_healthcheck_sklearn_missing_is_not_fatal(monkeypatch, tmp_path):
    class Status:
        sklearn_model_available = False

    monkeypatch.setattr(availability, "get_ml_dependency_status", lambda: Status())
    cfg = WorkflowConfig(storage_db_path=str(tmp_path / "workflow.db"), healthcheck_audit_path=str(tmp_path / "audit.jsonl"))
    result = run_startup_healthcheck(cfg, root=tmp_path)
    assert result["ok"] is True
    assert result["mode"] == "degraded_ml_disabled"


def test_healthcheck_writes_audit_jsonl(tmp_path):
    audit = tmp_path / "runtime" / "audit" / "healthcheck.jsonl"
    cfg = WorkflowConfig(storage_db_path=str(tmp_path / "workflow.db"), healthcheck_audit_path=str(audit))
    run_startup_healthcheck(cfg, root=tmp_path)
    assert audit.exists()
    assert Path(audit).read_text(encoding="utf-8").strip()
