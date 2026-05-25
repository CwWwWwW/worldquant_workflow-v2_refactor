from __future__ import annotations

from typing import Any

from wq_workflow.data.json_utils import json_loads_safe, safe_float

try:
    from .counterfactual_dataset import CounterfactualDatasetLoader
    from .counterfactual_evaluator import CounterfactualEvaluator
    from .counterfactual_features import CounterfactualFeatureBuilder
    from .counterfactual_metrics import CounterfactualMetricsCalculator
    from .counterfactual_neighbors import CounterfactualNeighborIndex
    from .counterfactual_repository import CounterfactualRepository
    from .counterfactual_reporter import CounterfactualReporter
    from .service import CounterfactualService
except Exception:  # pragma: no cover - preserves legacy estimator import if optional modules fail.
    CounterfactualDatasetLoader = None  # type: ignore
    CounterfactualEvaluator = None  # type: ignore
    CounterfactualFeatureBuilder = None  # type: ignore
    CounterfactualMetricsCalculator = None  # type: ignore
    CounterfactualNeighborIndex = None  # type: ignore
    CounterfactualRepository = None  # type: ignore
    CounterfactualReporter = None  # type: ignore
    CounterfactualService = None  # type: ignore


def _action_key(action: dict[str, Any] | None) -> str:
    data = action if isinstance(action, dict) else {}
    return str(data.get("action_id") or data.get("id") or data.get("action_name") or data.get("action_type") or data.get("type") or "")


def _context_similar(a: dict[str, Any], b: dict[str, Any]) -> bool:
    if not a or not b:
        return True
    keys = ("task_name", "mutation_type", "behavior_family", "candidate_source", "alpha_id")
    comparable = [k for k in keys if a.get(k) is not None and b.get(k) is not None]
    if not comparable:
        return True
    return any(str(a.get(k)) == str(b.get(k)) for k in comparable)


class CounterfactualEstimator:
    def __init__(self, repositories: Any, config: Any, logger: Any | None = None) -> None:
        self.repositories = repositories
        self.config = config
        self.logger = logger

    def estimate_action_outcome(self, context: dict, action: dict, decision_type: str) -> dict:
        decision_repo = getattr(self.repositories, "decision", None)
        min_count = int(getattr(self.config, "support_min_action_count", 10) or 10)
        if decision_repo is None:
            return self._insufficient(0)
        try:
            decisions = decision_repo.list_recent_decisions(decision_type=decision_type, limit=int(getattr(self.config, "offline_replay_max_decisions", 5000) or 5000))
        except Exception:
            decisions = []
        target_key = _action_key(action)
        samples: list[dict[str, Any]] = []
        for row in decisions:
            chosen = json_loads_safe(row.get("chosen_action_json"), {})
            ctx = json_loads_safe(row.get("context_json"), {})
            if target_key and _action_key(chosen) != target_key:
                continue
            if not _context_similar(context if isinstance(context, dict) else {}, ctx if isinstance(ctx, dict) else {}):
                continue
            outcome = decision_repo.get_outcome_for_decision(str(row.get("decision_id") or ""))
            if outcome:
                samples.append(outcome)
        if len(samples) < min_count:
            return self._insufficient(len(samples))
        reward = sum(safe_float(s.get("reward_delta", s.get("reward")), 0.0) for s in samples) / len(samples)
        success = sum(1 for s in samples if s.get("success") in {1, True}) / len(samples)
        risk = sum(safe_float(s.get("platform_sc_abs_max"), 0.0) for s in samples) / len(samples)
        failure = 1.0 - success
        confidence = min(0.95, len(samples) / max(float(min_count * 3), 1.0))
        return {
            "estimated_reward_delta": float(reward),
            "estimated_success_rate": float(success),
            "estimated_sc_risk": float(risk),
            "estimated_failure_rate": float(failure),
            "support_count": len(samples),
            "confidence": float(confidence),
            "support_status": "sufficient",
            "uses_real_unexecuted_reward": False,
        }

    def estimate_parent_outcome(self, parent_features: dict) -> dict:
        return self.estimate_action_outcome(parent_features or {}, parent_features or {}, "parent_selection")

    def estimate_policy_action_outcome(self, context: dict, action: dict) -> dict:
        return self.estimate_action_outcome(context or {}, action or {}, "policy_action")

    def estimate_simulator_decision_outcome(self, context: dict, decision: dict) -> dict:
        return self.estimate_action_outcome(context or {}, decision or {}, "simulator_decision")

    def _insufficient(self, support_count: int) -> dict:
        min_count = int(getattr(self.config, "support_min_action_count", 10) or 10)
        confidence = 0.0 if min_count <= 0 else min(0.25, float(support_count) / float(min_count) * 0.25)
        return {
            "estimated_reward_delta": 0.0,
            "estimated_success_rate": 0.0,
            "estimated_sc_risk": 0.0,
            "estimated_failure_rate": 0.0,
            "support_count": int(support_count),
            "confidence": float(confidence),
            "support_status": "insufficient",
            "uses_real_unexecuted_reward": False,
        }
