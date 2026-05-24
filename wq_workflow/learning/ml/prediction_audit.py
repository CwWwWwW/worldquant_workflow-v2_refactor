from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from wq_workflow.time_utils import utc_now_iso


def json_dumps_safe(obj: Any) -> str:
    try:
        from wq_workflow.data.json_utils import json_dumps_safe as _dumps

        return _dumps(obj)
    except Exception:
        try:
            return json.dumps(obj, ensure_ascii=False, default=str)
        except Exception:
            return "{}"


class PredictionAuditWriter:
    def __init__(self, db_conn: Any, logger: Any | None = None) -> None:
        self.conn = db_conn
        self.logger = logger

    def audit_prediction(
        self,
        *,
        task_name: str,
        alpha_id: str | None,
        model_version: str = "",
        features: dict[str, Any] | None = None,
        prediction: dict[str, Any] | None = None,
        confidence: float | None = None,
        final_decision: str = "",
        final_source: str = "",
        raw_payload: dict[str, Any] | None = None,
    ) -> str | None:
        prediction_id = str(uuid.uuid4())
        try:
            self.conn.execute(
                """
                INSERT OR REPLACE INTO ml_prediction_audit
                (prediction_id, task_name, alpha_id, model_version, features_json,
                 prediction_json, confidence, final_decision, final_source, created_at, raw_payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    prediction_id,
                    task_name,
                    alpha_id,
                    model_version or "",
                    json_dumps_safe(features or {}),
                    json_dumps_safe(prediction or {}),
                    confidence,
                    final_decision or "",
                    final_source or "",
                    utc_now_iso(timespec="seconds"),
                    json_dumps_safe(raw_payload or {}),
                ),
            )
            self.conn.commit()
            return prediction_id
        except Exception as exc:
            try:
                if self.logger is not None:
                    self.logger.warning("failed to audit ML prediction: %s", exc)
            except Exception:
                pass
            return None


class PredictionAuditService:
    def __init__(self, *, repository: Any | None = None, storage: Any | None = None, db_path: str | Path | None = None, logger: Any | None = None) -> None:
        self.logger = logger
        if repository is not None:
            self.repository = repository
        else:
            from wq_workflow.data.repositories import MLRepository

            self.repository = MLRepository(storage=storage, db_path=db_path)

    def audit(
        self,
        *,
        task_name: str,
        alpha_id: str = "",
        model_version: str = "",
        features: dict[str, Any] | None = None,
        prediction: dict[str, Any] | None = None,
        confidence: float | None = None,
        final_decision: str = "",
        final_source: str = "",
        raw_payload: dict[str, Any] | None = None,
    ) -> str:
        prediction_id = uuid.uuid4().hex
        try:
            self.repository.audit_prediction(
                task_name=task_name,
                prediction_id=prediction_id,
                alpha_id=alpha_id,
                model_version=model_version or "",
                features=features or {},
                prediction={**(prediction or {}), **({"explain": "not_provided"} if isinstance(prediction, dict) and "explain" not in prediction else {})},
                confidence=confidence,
                final_decision=final_decision,
                final_source=final_source,
                raw_payload=raw_payload or {},
            )
        except Exception as exc:
            try:
                if self.logger is not None:
                    self.logger.warning("prediction audit write failed: %s", exc)
            except Exception:
                pass
        return prediction_id

    def record(self, **kwargs: Any) -> str:
        """Compatibility alias for predictors that historically called record().

        Keep this adapter permissive so older/newer predictors can pass the
        common audit fields without making the prediction path fail.
        """
        allowed = {
            "task_name",
            "alpha_id",
            "model_version",
            "features",
            "prediction",
            "confidence",
            "final_decision",
            "final_source",
            "raw_payload",
        }
        payload = {key: kwargs.get(key) for key in allowed if key in kwargs}
        payload.setdefault("task_name", str(kwargs.get("task_name") or ""))
        payload.setdefault("alpha_id", str(kwargs.get("alpha_id") or ""))
        payload.setdefault("model_version", str(kwargs.get("model_version") or ""))
        payload.setdefault("features", kwargs.get("features") or {})
        payload.setdefault("prediction", kwargs.get("prediction") or {})
        payload.setdefault("confidence", kwargs.get("confidence"))
        payload.setdefault("final_decision", str(kwargs.get("final_decision") or ""))
        payload.setdefault("final_source", str(kwargs.get("final_source") or ""))
        payload.setdefault("raw_payload", kwargs.get("raw_payload") or {})
        return self.audit(**payload)


class PredictionAuditLogger(PredictionAuditService):
    def record(
        self,
        *,
        task_name: str,
        alpha_id: str = "",
        model_version: str = "",
        features: dict[str, Any] | None = None,
        prediction: dict[str, Any] | None = None,
        confidence: float | None = None,
        final_decision: str = "",
        final_source: str = "",
        raw_payload: dict[str, Any] | None = None,
    ) -> str:
        return self.audit(
            task_name=task_name,
            alpha_id=alpha_id,
            model_version=model_version or "",
            features=features or {},
            prediction={**(prediction or {}), **({"explain": "not_provided"} if isinstance(prediction, dict) and "explain" not in prediction else {})},
            confidence=confidence,
            final_decision=final_decision,
            final_source=final_source,
            raw_payload=raw_payload or {},
        )


def safe_audit_prediction(audit_logger: Any, logger: Any | None = None, **kwargs: Any) -> Any | None:
    """Best-effort prediction audit writer.

    Audit failures must never convert a successful prediction into a model
    failure, because audit is an optional side effect.
    """
    if audit_logger is None:
        return None
    try:
        fn = getattr(audit_logger, "record", None)
        if not callable(fn):
            fn = getattr(audit_logger, "audit", None)
        if callable(fn):
            return fn(**kwargs)
    except Exception as exc:
        try:
            if logger is not None:
                logger.warning("ML prediction audit failed but prediction will continue: %s", exc)
        except Exception:
            pass
    return None
