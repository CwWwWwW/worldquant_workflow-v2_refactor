from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any


def _json_line(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")


def _resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def run_startup_healthcheck(
    config: Any,
    *,
    storage: Any | None = None,
    model_registry: Any | None = None,
    logger: Any | None = None,
    root: str | Path | None = None,
) -> dict[str, Any]:
    """Lightweight startup stability check for phase 1.

    No long-term guard, lifecycle, retraining, rollback, online evaluation, or
    drift governance is performed here.
    """
    from wq_workflow import paths
    from wq_workflow.data.migrations import initialize_refactor_tables
    from wq_workflow.learning.ml.availability import get_ml_dependency_status
    from wq_workflow.storage.schema import initialize_schema
    from wq_workflow.workflow.pipeline import has_observe_only_critical_steps, observe_only_critical_step_names
    from wq_workflow.workflow.steps import DEFAULT_STEP_CLASSES

    root_path = Path(root or paths.ROOT)
    warnings: list[str] = []
    errors: list[str] = []
    auto_fixes: list[str] = []
    mode = "normal"
    observability_status: dict[str, Any] = {
        "enabled": bool(getattr(config, "enable_observability_metrics", True)),
        "ready": False,
        "mode": getattr(config, "observability_mode", "metrics_only"),
    }
    observability_alert_status: dict[str, Any] = {
        "alerts_enabled": bool(getattr(config, "enable_observability_alerts", False)),
        "drift_detection_enabled": bool(getattr(config, "enable_observability_drift_detection", False)),
        "diagnosis_enabled": bool(getattr(config, "enable_observability_diagnosis", False)),
        "ready": False,
        "mode": "advisory",
    }
    explainability_status: dict[str, Any] = {
        "enabled": bool(getattr(config, "enable_run_explainability", False)),
        "ready": False,
        "mode": "explain_only",
        "auto_action_allowed": False,
    }

    def warn(message: str) -> None:
        warnings.append(message)
        try:
            if logger is not None:
                logger.warning("startup healthcheck: %s", message)
        except Exception:
            pass

    db_path = getattr(getattr(storage, "config", None), "db_path", None) or getattr(config, "storage_db_path", "runtime/db/workflow.db")
    db_path = _resolve_path(root_path, db_path)
    try:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db_path)
        try:
            initialize_schema(conn)
            initialize_refactor_tables(conn)
            conn.commit()
            auto_fixes.append("schema_initialized")
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            for table in ("ml_model_registry", "ml_prediction_audit", "ml_training_samples", "ml_model_events", "ml_online_evaluation"):
                if table not in tables:
                    errors.append(f"missing_ml_table:{table}")
            if bool(getattr(config, "enable_observability_metrics", True)):
                missing_observability_tables: list[str] = []
                for table in ("observability_metrics", "observability_source_status", "observability_snapshots", "observability_summaries"):
                    if table not in tables:
                        missing_observability_tables.append(table)
                        warn(f"missing_observability_table:{table}")
                status_path = _resolve_path(root_path, getattr(config, "observability_metrics_status_path", "runtime/status/observability_metrics.json"))
                try:
                    status_path.parent.mkdir(parents=True, exist_ok=True)
                    auto_fixes.append("observability_status_path_ready")
                    observability_status.update({"ready": not missing_observability_tables, "status_path": str(status_path)})
                except Exception as exc:
                    warn(f"observability_status_path_unavailable:{exc}")
                    observability_status.update({"ready": False, "status_path": str(status_path), "error": str(exc)})
            else:
                observability_status["ready"] = True
            missing_alert_tables: list[str] = []
            for table in (
                "observability_drift_rules",
                "observability_drift_signals",
                "observability_alert_rules",
                "observability_alert_events",
                "observability_health_diagnoses",
                "observability_health_reports",
            ):
                if table not in tables:
                    missing_alert_tables.append(table)
                    warn(f"missing_observability_alert_table:{table}")
            alert_path = _resolve_path(root_path, getattr(config, "observability_alerts_status_path", "runtime/status/observability_alerts.json"))
            diagnosis_path = _resolve_path(root_path, getattr(config, "observability_diagnosis_status_path", "runtime/status/health_diagnosis.json"))
            path_ready = True
            for path in (alert_path, diagnosis_path):
                try:
                    path.parent.mkdir(parents=True, exist_ok=True)
                except Exception as exc:
                    path_ready = False
                    warn(f"observability_advisory_status_path_unavailable:{path}:{exc}")
            if path_ready:
                auto_fixes.append("observability_advisory_status_paths_ready")
            observability_alert_status.update({
                "ready": not missing_alert_tables and path_ready,
                "alert_status_path": str(alert_path),
                "diagnosis_status_path": str(diagnosis_path),
            })
            missing_explain_tables: list[str] = []
            for table in (
                "observability_explanation_evidence",
                "observability_decision_traces",
                "observability_run_explanations",
                "observability_daily_reports",
                "observability_stage_reports",
            ):
                if table not in tables:
                    missing_explain_tables.append(table)
                    warn(f"missing_observability_explainability_table:{table}")
            explain_paths = [
                _resolve_path(root_path, getattr(config, "run_explain_report_status_path", "runtime/status/run_explain_report.json")),
                _resolve_path(root_path, getattr(config, "daily_observability_report_status_path", "runtime/status/daily_observability_report.json")),
                _resolve_path(root_path, getattr(config, "stage7_summary_report_status_path", "runtime/status/stage7_summary_report.json")),
            ]
            explain_path_ready = True
            for path in explain_paths:
                try:
                    path.parent.mkdir(parents=True, exist_ok=True)
                except Exception as exc:
                    explain_path_ready = False
                    warn(f"observability_explainability_status_path_unavailable:{path}:{exc}")
            if explain_path_ready:
                auto_fixes.append("observability_explainability_status_paths_ready")
            explainability_status.update({
                "ready": not missing_explain_tables and explain_path_ready,
                "run_report_path": str(explain_paths[0]),
                "daily_report_path": str(explain_paths[1]),
                "stage_report_path": str(explain_paths[2]),
            })
        finally:
            conn.close()
    except Exception as exc:
        errors.append(f"workflow_db_unavailable:{exc}")

    candidate_path = getattr(paths, "CANDIDATE_POOL_FILE", root_path / "memory" / "evolution" / "candidate_pool.json")
    try:
        candidate_path = _resolve_path(root_path, candidate_path)
        if candidate_path.exists():
            json.loads(candidate_path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        warn(f"candidate_pool_json_broken:{exc}")
        if bool(getattr(config, "healthcheck_auto_repair", True)):
            backup = candidate_path.with_name(f"{candidate_path.name}.broken.{datetime.now().strftime('%Y%m%d%H%M%S')}.bak")
            try:
                backup.parent.mkdir(parents=True, exist_ok=True)
                backup.write_text(candidate_path.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
                auto_fixes.append(f"candidate_pool_backed_up:{backup}")
            except Exception as backup_exc:
                warn(f"candidate_pool_backup_failed:{backup_exc}")

    steps = [cls(None) for cls in DEFAULT_STEP_CLASSES]
    if bool(getattr(config, "enable_refactored_pipeline", False)) and has_observe_only_critical_steps(steps):
        names = observe_only_critical_step_names(steps)
        warn(f"refactored_pipeline_observe_only_critical_steps:{names}")
        if bool(getattr(config, "healthcheck_force_legacy_on_critical_warning", True)):
            mode = "safe_legacy"
            auto_fixes.append("runtime_force_legacy_recommended")

    deps = get_ml_dependency_status()
    if not deps.sklearn_model_available:
        warn("ml_dependencies_unavailable; ML model prediction will degrade safely")
        mode = "degraded_ml_disabled" if mode == "normal" else mode

    if model_registry is not None:
        try:
            consistency = model_registry.check_registry_consistency()
            if not consistency.get("ok", False):
                warn(f"active_model_registry_inconsistent:{consistency.get('issues', [])}")
                if bool(getattr(config, "healthcheck_disable_broken_models", True)):
                    for issue in consistency.get("issues", []):
                        task = issue.get("task_name")
                        if task and issue.get("issue") in {"broken_active_pointer", "missing_model_file", "missing_db_record", "schema_missing"}:
                            if model_registry.disable_active_model(task, reason="startup_healthcheck_inconsistent_registry"):
                                auto_fixes.append(f"disabled_broken_active_model:{task}")
                    mode = "degraded_ml_disabled" if mode == "normal" else mode
        except Exception as exc:
            warn(f"registry_consistency_check_failed:{exc}")

    if bool(getattr(config, "enable_learning_governance", True)):
        try:
            from wq_workflow.governance.service import LearningGovernanceService

            governance = LearningGovernanceService(config=config, model_registry=model_registry, storage=storage, db_path=db_path, logger=logger, root=root_path)
            governance_result = governance.startup_check()
            if not governance_result.get("ok", False):
                warn(f"governance_startup_check_warning:{governance_result}")
                mode = "degraded_ml_disabled" if mode == "normal" else mode
            auto_fixes.append("governance_startup_check")
            for flag, task in (
                ("enable_parent_model_decision", "parent"),
                ("enable_policy_model_decision", "policy"),
                ("enable_simulator_model_skip", "simulator"),
                ("enable_sc_model_fallback", "sc"),
            ):
                if bool(getattr(config, flag, False)):
                    decision_type = {
                        "sc": "sc_fallback",
                        "parent": "parent_selection",
                        "policy": "mutation_policy",
                        "simulator": "simulator_skip",
                    }.get(task, task)
                    decision = governance.allow_hard_decision(task, decision_type, config)
                    if not decision.allowed:
                        warn(f"unsafe_hard_decision_flag:{flag}:{decision.reason}")
        except Exception as exc:
            warn(f"governance_startup_check_failed:{exc}")

    result = {"ok": not errors, "mode": mode, "warnings": warnings, "errors": errors, "auto_fixes": auto_fixes, "observability": observability_status, "observability_alerts": observability_alert_status, "observability_explainability": explainability_status}
    try:
        audit_path = _resolve_path(root_path, getattr(config, "healthcheck_audit_path", "runtime/audit/healthcheck.jsonl"))
        _json_line(audit_path, {"timestamp": datetime.now().isoformat(timespec="seconds"), **result})
    except Exception as exc:
        warnings.append(f"healthcheck_audit_write_failed:{exc}")
        result["warnings"] = warnings
    return result
