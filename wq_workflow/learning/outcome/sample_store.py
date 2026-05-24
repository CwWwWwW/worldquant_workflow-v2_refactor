from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from wq_workflow.data.json_utils import json_dumps_safe, safe_float
from wq_workflow.alpha.representation.features import build_alpha_representation


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _get(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


class OutcomeSampleStore:
    def __init__(self, *, storage: Any | None = None, db_path: str | Path | None = None, logger: Any | None = None, config: Any | None = None) -> None:
        self.storage = storage
        self.db_path = Path(db_path) if db_path is not None else getattr(getattr(storage, "config", None), "db_path", None)
        self.logger = logger
        self.config = config

    def _features(self, candidate: dict[str, Any], metrics: dict[str, Any], workflow_context: Any | None) -> dict[str, Any]:
        features = dict(candidate.get("features") or metrics or {})
        if bool(getattr(self.config, "enable_alpha_representation", True)):
            try:
                rep = getattr(workflow_context, "alpha_representation", None)
                rep = candidate.get("alpha_representation") or rep
                if rep is None:
                    expression = str(candidate.get("expression") or candidate.get("code") or "")
                    rep = build_alpha_representation(expression)
                if rep is not None:
                    features.update(getattr(rep, "features", {}) or {})
                    if hasattr(rep, "summary"):
                        features.setdefault("alpha_representation", rep.summary())
            except Exception:
                pass
        platform_sc = _get(workflow_context, "platform_sc", {}) or candidate.get("platform_sc") or {}
        features.setdefault("candidate_source", candidate.get("candidate_source"))
        features.setdefault("mutation_type", candidate.get("mutation_type"))
        features.setdefault("parent_reward", candidate.get("parent_reward") or (_get(workflow_context, "parent", {}) or {}).get("reward") if isinstance(_get(workflow_context, "parent", {}) or {}, dict) else None)
        features.setdefault("estimated_self_corr", candidate.get("estimated_self_corr"))
        features.setdefault("final_sc", candidate.get("final_sc") or (platform_sc.get("abs_max") if isinstance(platform_sc, dict) else None))
        return features

    def record_simulator_outcome(self, candidate: dict[str, Any] | None = None, prediction: dict[str, Any] | None = None, workflow_context: Any | None = None) -> str | None:
        candidate = candidate if isinstance(candidate, dict) else (_get(workflow_context, "candidate", {}) or {})
        prediction = prediction if isinstance(prediction, dict) else (_get(workflow_context, "simulator_prediction", {}) or {})
        alpha_id = str(candidate.get("alpha_id") or _get(workflow_context, "alpha_id", "") or "")
        if not alpha_id:
            return None
        metrics = _get(workflow_context, "metrics", {}) or candidate.get("metrics") or {}
        quality = _get(workflow_context, "quality", {}) or {}
        reward = _get(workflow_context, "reward", candidate.get("reward"))
        features = self._features(candidate, metrics, workflow_context)
        sample_id = "simulator:" + hashlib.sha1(f"{alpha_id}:{reward}".encode("utf-8", errors="ignore")).hexdigest()[:20]
        if not self.db_path:
            return sample_id
        try:
            from wq_workflow.storage.schema import initialize_schema

            conn = sqlite3.connect(self.db_path)
            try:
                initialize_schema(conn)
                conn.execute(
                    """
                    INSERT OR REPLACE INTO simulator_training_samples
                    (sample_id, alpha_id, features_json, prediction_json, backtest_success, quality_passed, reward,
                     fitness, sharpe, turnover, failure_type, created_at, raw_payload)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        sample_id,
                        alpha_id,
                        json_dumps_safe(features),
                        json_dumps_safe(prediction),
                        None if quality.get("backtest_success") is None else (1 if quality.get("backtest_success") else 0),
                        None if quality.get("passed") is None else (1 if quality.get("passed") else 0),
                        safe_float(reward),
                        safe_float(metrics.get("fitness")),
                        safe_float(metrics.get("sharpe")),
                        safe_float(metrics.get("turnover")),
                        str(quality.get("failure_type") or ""),
                        _now(),
                        json_dumps_safe({"candidate": candidate, "prediction": prediction, "workflow": getattr(workflow_context, "__dict__", {})}),
                    ),
                )
                conn.commit()
            finally:
                conn.close()
            return sample_id
        except Exception as exc:
            try:
                if self.logger:
                    self.logger.warning("simulator sample write failed: %s", exc)
            except Exception:
                pass
            return None

    def record(self, **kwargs: Any) -> str | None:
        return self.record_simulator_outcome(**kwargs)
