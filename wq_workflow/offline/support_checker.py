from __future__ import annotations

from typing import Any

from wq_workflow.data.json_utils import json_loads_safe
from .counterfactual import _action_key, _context_similar


class SupportChecker:
    def __init__(self, repositories: Any, config: Any, logger: Any | None = None) -> None:
        self.repositories = repositories
        self.config = config
        self.logger = logger

    def check_decision_support(self, decision_type: str, recommendations: list[dict]) -> dict:
        recs = [r for r in recommendations or [] if isinstance(r, dict)]
        if not recs:
            return {"support_pass": False, "support_coverage": 0.0, "min_action_count": self._min_action(), "unsupported_actions": [], "warnings": ["no_recommendations"]}
        results = [self.check_action_support(decision_type, _action_key(r), r.get("context") if isinstance(r.get("context"), dict) else None) for r in recs]
        passed = [bool(r.get("support_pass")) for r in results]
        unsupported: list[str] = []
        warnings: list[str] = []
        for rec, result in zip(recs, results):
            if not result.get("support_pass"):
                unsupported.append(_action_key(rec))
            warnings.extend(list(result.get("warnings") or []))
        return {
            "support_pass": all(passed),
            "support_coverage": sum(1 for p in passed if p) / max(1, len(passed)),
            "min_action_count": self._min_action(),
            "unsupported_actions": unsupported,
            "warnings": warnings,
        }

    def check_action_support(self, action_type: str, action_name: str, context: dict | None = None) -> dict:
        decision_repo = getattr(self.repositories, "decision", None)
        min_action = self._min_action()
        min_context = int(getattr(self.config, "support_min_context_count", 20) or 20)
        if decision_repo is None:
            return self._result(False, 0.0, 0, [action_name], ["decision_repository_unavailable"])
        try:
            rows = decision_repo.list_recent_decisions(decision_type=action_type, limit=int(getattr(self.config, "offline_replay_max_decisions", 5000) or 5000))
        except Exception:
            rows = []
        action_count = 0
        context_count = 0
        for row in rows:
            chosen = json_loads_safe(row.get("chosen_action_json"), {})
            if action_name and _action_key(chosen) != str(action_name):
                continue
            action_count += 1
            row_context = json_loads_safe(row.get("context_json"), {})
            if _context_similar(context or {}, row_context if isinstance(row_context, dict) else {}):
                context_count += 1
        warnings: list[str] = []
        if action_count < min_action:
            warnings.append("action_count_below_minimum")
        if context is not None and context_count < min_context:
            warnings.append("context_count_below_minimum")
        support_pass = action_count >= min_action and (context is None or context_count >= min_context)
        coverage = min(1.0, min(action_count / max(1, min_action), context_count / max(1, min_context) if context is not None else 1.0))
        return self._result(support_pass, coverage, action_count, [] if support_pass else [action_name], warnings, context_count=context_count)

    def check_parent_support(self, parent_features: dict) -> dict:
        family = str((parent_features or {}).get("behavior_family") or (parent_features or {}).get("family") or "")
        return self.check_action_support("parent_selection", family or _action_key(parent_features or {}), parent_features or {})

    def check_strategy_support(self, strategy_id: str) -> dict:
        strategy_repo = getattr(self.repositories, "strategy", None)
        min_context = int(getattr(self.config, "support_min_context_count", 20) or 20)
        if strategy_repo is None:
            return self._result(False, 0.0, 0, [strategy_id], ["strategy_repository_unavailable"])
        try:
            rows = strategy_repo.list_strategy_decisions(strategy_id=strategy_id, limit=max(min_context, 1000))
        except Exception:
            rows = []
        shadow_count = sum(1 for row in rows if row.get("shadow") in {1, True})
        selected_count = sum(1 for row in rows if row.get("selected") in {1, True})
        support_count = shadow_count + selected_count
        support_pass = support_count >= min_context
        return {
            "support_pass": support_pass,
            "support_coverage": min(1.0, support_count / max(1, min_context)),
            "min_action_count": self._min_action(),
            "support_count": support_count,
            "shadow_count": shadow_count,
            "selected_count": selected_count,
            "unsupported_actions": [] if support_pass else [strategy_id],
            "warnings": [] if support_pass else ["strategy_shadow_decisions_below_minimum"],
        }

    def _min_action(self) -> int:
        return int(getattr(self.config, "support_min_action_count", 10) or 10)

    def _result(self, support_pass: bool, coverage: float, action_count: int, unsupported: list[str], warnings: list[str], **extra: Any) -> dict:
        return {
            "support_pass": bool(support_pass),
            "support_coverage": float(coverage),
            "min_action_count": self._min_action(),
            "action_count": int(action_count),
            "unsupported_actions": unsupported,
            "warnings": warnings,
            **extra,
        }
