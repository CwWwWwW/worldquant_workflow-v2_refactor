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


class ParentSampleStore:
    def __init__(self, *, storage: Any | None = None, db_path: str | Path | None = None, logger: Any | None = None, config: Any | None = None) -> None:
        self.storage = storage
        self.db_path = Path(db_path) if db_path is not None else getattr(getattr(storage, "config", None), "db_path", None)
        self.logger = logger
        self.config = config

    def _build_representation(self, expression: str, existing: Any = None) -> Any | None:
        if existing is not None:
            return existing
        if not bool(getattr(self.config, "enable_alpha_representation", True)):
            return None
        try:
            return build_alpha_representation(expression or "")
        except Exception:
            return None

    def _parent_features(self, parent: dict[str, Any], workflow_context: Any | None) -> dict[str, Any]:
        expression = str(parent.get("expression") or parent.get("code") or "")
        representation = self._build_representation(expression, parent.get("alpha_representation"))
        metrics = parent.get("metrics") if isinstance(parent.get("metrics"), dict) else {}
        platform_sc = parent.get("platform_sc") if isinstance(parent.get("platform_sc"), dict) else {}
        out: dict[str, Any] = {
            "parent": dict(parent),
            "parent_reward": parent.get("reward"),
            "parent_fitness": parent.get("fitness", metrics.get("fitness")),
            "parent_sharpe": parent.get("sharpe", metrics.get("sharpe")),
            "parent_turnover": parent.get("turnover", metrics.get("turnover")),
            "parent_platform_sc_abs_max": platform_sc.get("abs_max"),
            "parent_final_sc": parent.get("final_sc"),
            "parent_lineage_depth": parent.get("lineage_depth"),
            "parent_behavior_family": parent.get("behavior_family"),
        }
        if representation is not None and hasattr(representation, "summary"):
            try:
                out["alpha_representation"] = representation.summary()
                out["alpha_representation_features"] = getattr(representation, "features", {}) or {}
                out["parent_behavior_family"] = out.get("parent_behavior_family") or getattr(representation, "behavior_family", "")
            except Exception:
                pass
        return out

    def record_parent_outcome(self, parent: dict[str, Any] | None = None, child: dict[str, Any] | None = None, workflow_context: Any | None = None) -> str | None:
        if not parent or not child:
            return None
        parent_alpha_id = str(parent.get("alpha_id") or parent.get("id") or "")
        child_alpha_id = str(child.get("alpha_id") or child.get("id") or _get(workflow_context, "alpha_id", ""))
        if not parent_alpha_id or not child_alpha_id:
            return None
        metrics = _get(workflow_context, "metrics", {}) or child.get("metrics") or {}
        platform_sc = _get(workflow_context, "platform_sc", {}) or child.get("platform_sc") or {}
        quality = _get(workflow_context, "quality", {}) or {}
        reward = _get(workflow_context, "reward", child.get("reward"))
        reward_delta = child.get("reward_delta") if isinstance(child, dict) else None
        mutation_type = child.get("mutation_type") or _get(workflow_context, "mutation_type", "")
        sample_id = "parent:" + hashlib.sha1(f"{parent_alpha_id}:{child_alpha_id}:{reward}".encode("utf-8", errors="ignore")).hexdigest()[:20]
        if not self.db_path:
            return sample_id
        try:
            from wq_workflow.storage.schema import initialize_schema

            conn = sqlite3.connect(self.db_path)
            try:
                initialize_schema(conn)
                conn.execute(
                    """
                    INSERT OR REPLACE INTO parent_selection_samples
                    (sample_id, parent_alpha_id, child_alpha_id, parent_features_json, child_metrics_json, child_reward,
                     reward_delta, child_success, child_platform_sc_abs_max, mutation_type, created_at, raw_payload)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        sample_id,
                        parent_alpha_id,
                        child_alpha_id,
                        json_dumps_safe(self._parent_features(parent, workflow_context)),
                        json_dumps_safe(metrics),
                        safe_float(reward),
                        safe_float(reward_delta),
                        None if quality.get("passed") is None else (1 if quality.get("passed") else 0),
                        safe_float(platform_sc.get("abs_max") if isinstance(platform_sc, dict) else None),
                        str(mutation_type or ""),
                        _now(),
                        json_dumps_safe({"parent": parent, "child": child, "workflow": getattr(workflow_context, "__dict__", {})}),
                    ),
                )
                conn.commit()
            finally:
                conn.close()
            return sample_id
        except Exception as exc:
            try:
                if self.logger:
                    self.logger.warning("parent sample write failed: %s", exc)
            except Exception:
                pass
            return None

    def record(self, **kwargs: Any) -> str | None:
        return self.record_parent_outcome(**kwargs)
