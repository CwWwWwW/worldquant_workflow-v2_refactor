from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from wq_workflow.data.json_utils import json_dumps_safe, safe_float
from wq_workflow.data.repositories import MLRepository
from wq_workflow.alpha.representation.features import build_alpha_representation


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _valid_abs(value: Any) -> float | None:
    number = safe_float(value)
    return abs(number) if number is not None else None


def _feature_value(features: dict[str, Any], key: str) -> Any:
    return features.get(key)


class SCSampleStore:
    def __init__(self, *, storage: Any | None = None, db_path: str | Path | None = None, ml_repository: Any | None = None, logger: Any | None = None, config: Any | None = None) -> None:
        self.storage = storage
        self.db_path = Path(db_path) if db_path is not None else getattr(getattr(storage, "config", None), "db_path", None)
        self.ml_repository = ml_repository or MLRepository(storage=storage, db_path=db_path)
        self.logger = logger
        self.config = config

    def _representation(self, expression: str, features: dict[str, Any], context: dict[str, Any], raw_payload: dict[str, Any] | None) -> Any | None:
        if not bool(getattr(self.config, "enable_alpha_representation", True)):
            return None
        for source in (features, context, raw_payload or {}):
            rep = source.get("alpha_representation") if isinstance(source, dict) else None
            if rep is not None:
                return rep
        wf = (raw_payload or {}).get("workflow_context") if isinstance(raw_payload, dict) else None
        rep = getattr(wf, "alpha_representation", None)
        if rep is not None:
            return rep
        try:
            return build_alpha_representation(expression or "")
        except Exception:
            return None

    def record_if_complete(
        self,
        *,
        alpha_id: str = "",
        expression: str = "",
        platform_sc: dict[str, Any] | None = None,
        features: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
        raw_payload: dict[str, Any] | None = None,
    ) -> str | None:
        platform_sc = platform_sc if isinstance(platform_sc, dict) else {}
        if platform_sc.get("status") != "complete":
            return None
        abs_max = _valid_abs(platform_sc.get("abs_max"))
        if abs_max is None:
            return None
        features = features if isinstance(features, dict) else {}
        context = context if isinstance(context, dict) else {}
        representation = self._representation(expression, features, context, raw_payload)
        rep_features = getattr(representation, "features", None)
        full_features = {
            "expression_length": _feature_value(features, "expression_length") if _feature_value(features, "expression_length") is not None else len(expression or ""),
            "operator_count": _feature_value(features, "operator_count"),
            "field_count": _feature_value(features, "field_count"),
            "ast_depth": _feature_value(features, "ast_depth"),
            "estimated_self_corr": _feature_value(features, "estimated_self_corr"),
            "sharpe": _feature_value(features, "sharpe"),
            "fitness": _feature_value(features, "fitness"),
            "turnover": _feature_value(features, "turnover"),
            "margin": _feature_value(features, "margin"),
        }
        if isinstance(rep_features, dict):
            full_features.update(rep_features)
        for key, value in features.items():
            if key != "alpha_representation":
                full_features.setdefault(key, value)
        label = {
            "platform_sc_abs_max": abs_max,
            "platform_sc_max": safe_float(platform_sc.get("max")),
            "platform_sc_min": safe_float(platform_sc.get("min")),
        }
        full_context = {
            "alpha_id": alpha_id,
            "expression": expression,
            "behavior_family": context.get("behavior_family"),
            "mutation_type": context.get("mutation_type"),
            "candidate_source": context.get("candidate_source"),
        }
        for key, value in context.items():
            if key != "alpha_representation":
                full_context.setdefault(key, value)
        if representation is not None and hasattr(representation, "summary"):
            try:
                full_context.setdefault("alpha_representation", representation.summary())
            except Exception:
                pass
        basis = f"{alpha_id}:{expression}:{abs_max}"
        text_hash = hashlib.sha1(basis.encode("utf-8", errors="ignore")).hexdigest()[:16]
        sample_id = f"sc:{alpha_id}:{text_hash}"
        payload = raw_payload or {"platform_sc": platform_sc, "context": full_context}
        try:
            self.ml_repository.insert_training_sample("sc", sample_id, alpha_id, full_features, label, full_context, payload)
            if not self.db_path:
                return sample_id
            from wq_workflow.storage.schema import initialize_schema

            conn = sqlite3.connect(self.db_path)
            try:
                initialize_schema(conn)
                conn.execute(
                    """
                    INSERT OR REPLACE INTO sc_training_samples
                    (sample_id, alpha_id, expression, platform_sc_abs_max, platform_sc_status, features_json, label_json,
                     context_json, raw_payload, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (sample_id, alpha_id, expression, abs_max, str(platform_sc.get("status") or ""), json_dumps_safe(full_features), json_dumps_safe(label), json_dumps_safe(full_context), json_dumps_safe(payload), _now()),
                )
                conn.commit()
            finally:
                conn.close()
            return sample_id
        except Exception as exc:
            try:
                if self.logger:
                    self.logger.warning("SC sample write failed: %s", exc)
            except Exception:
                pass
            return None

    def record_sample(self, **kwargs: Any) -> str | None:
        return self.record_if_complete(**kwargs)
