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


class PolicySampleStore:
    def __init__(self, *, storage: Any | None = None, db_path: str | Path | None = None, logger: Any | None = None, config: Any | None = None) -> None:
        self.storage = storage
        self.db_path = Path(db_path) if db_path is not None else getattr(getattr(storage, "config", None), "db_path", None)
        self.logger = logger
        self.config = config

    def _summary_for(self, item: Any, workflow_context: Any | None = None) -> dict[str, Any]:
        if not bool(getattr(self.config, "enable_alpha_representation", True)):
            return {}
        try:
            rep = getattr(workflow_context, "alpha_representation", None) if workflow_context is not None else None
            if isinstance(item, dict) and item.get("alpha_representation") is not None:
                rep = item.get("alpha_representation")
            if rep is None:
                expr = ""
                if isinstance(item, dict):
                    expr = str(item.get("expression") or item.get("code") or "")
                if expr:
                    rep = build_alpha_representation(expr)
            return rep.summary() if rep is not None and hasattr(rep, "summary") else {}
        except Exception:
            return {}

    def record_policy_outcome(self, decision_id: str | None = None, workflow_context: Any | None = None) -> str | None:
        decision_id = decision_id or _get(workflow_context, "policy_decision_id", None)
        if not decision_id:
            return None
        alpha_id = str(_get(workflow_context, "alpha_id", "") or "")
        decisions = _get(workflow_context, "decisions", []) or []
        decision = next((d for d in decisions if isinstance(d, dict) and d.get("decision_id") == decision_id), {})
        context = decision.get("context", {}) if isinstance(decision, dict) else {}
        available_actions = decision.get("available_actions", []) if isinstance(decision, dict) else []
        chosen_action = decision.get("chosen_action", {}) if isinstance(decision, dict) else {}
        candidate = _get(workflow_context, "candidate", {}) or {}
        parent = _get(workflow_context, "parent", {}) or {}
        full_context = dict(context) if isinstance(context, dict) else {}
        full_context.update(
            {
                "candidate_alpha_representation": self._summary_for(candidate, workflow_context),
                "parent_alpha_representation": self._summary_for(parent, None),
                "strategy_id": (_get(workflow_context, "strategy", {}) or {}).get("strategy_id") if isinstance(_get(workflow_context, "strategy", {}) or {}, dict) else None,
                "experiment_id": (_get(workflow_context, "experiment", {}) or {}).get("experiment_id") if isinstance(_get(workflow_context, "experiment", {}) or {}, dict) else None,
                "mutation_type": candidate.get("mutation_type") if isinstance(candidate, dict) else None,
                "available_actions": available_actions if isinstance(available_actions, list) else [],
                "chosen_action": chosen_action,
                "legacy_score": decision.get("legacy_score") if isinstance(decision, dict) else None,
                "model_score": decision.get("model_score") if isinstance(decision, dict) else None,
            }
        )
        quality = _get(workflow_context, "quality", {}) or {}
        platform_sc = _get(workflow_context, "platform_sc", {}) or {}
        sample_id = "policy:" + hashlib.sha1(f"{decision_id}:{alpha_id}".encode("utf-8", errors="ignore")).hexdigest()[:20]
        if not self.db_path:
            return sample_id
        try:
            from wq_workflow.storage.schema import initialize_schema

            conn = sqlite3.connect(self.db_path)
            try:
                initialize_schema(conn)
                conn.execute(
                    """
                    INSERT OR REPLACE INTO policy_training_samples
                    (sample_id, decision_id, alpha_id, context_json, available_actions_json, chosen_action_json,
                     reward_delta, success, failure_type, platform_sc_abs_max, created_at, raw_payload)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        sample_id,
                        decision_id,
                        alpha_id,
                        json_dumps_safe(full_context),
                        json_dumps_safe(available_actions if isinstance(available_actions, list) else []),
                        json_dumps_safe(chosen_action),
                        safe_float(decision.get("reward_delta") if isinstance(decision, dict) else None),
                        None if quality.get("passed") is None else (1 if quality.get("passed") else 0),
                        str(quality.get("failure_type") or ""),
                        safe_float(platform_sc.get("abs_max") if isinstance(platform_sc, dict) else None),
                        _now(),
                        json_dumps_safe({"decision": decision, "workflow": getattr(workflow_context, "__dict__", {})}),
                    ),
                )
                conn.commit()
            finally:
                conn.close()
            return sample_id
        except Exception as exc:
            try:
                if self.logger:
                    self.logger.warning("policy sample write failed: %s", exc)
            except Exception:
                pass
            return None

    def record(self, **kwargs: Any) -> str | None:
        return self.record_policy_outcome(**kwargs)
