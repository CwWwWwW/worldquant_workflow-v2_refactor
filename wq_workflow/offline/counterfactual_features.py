from __future__ import annotations

from typing import Any

from .schema import CounterfactualRequest, DecisionAction, ReplayRecord


class CounterfactualFeatureBuilder:
    """Build small, explainable fingerprints for conservative nearest-neighbor matching."""

    def action_fingerprint(self, action: DecisionAction | dict[str, Any] | None) -> dict[str, Any]:
        if action is None:
            return {}
        item = DecisionAction.from_dict(action)
        meta = item.metadata if isinstance(item.metadata, dict) else {}
        return _compact(
            {
                "action_id": item.action_id,
                "action_type": item.action_type,
                "action_source": item.source,
                "experiment_id": meta.get("experiment_id"),
                "arm_id": meta.get("arm_id") or item.action_id if item.action_type in {"arm", "experiment_arm"} else meta.get("arm_id"),
                "budget_plan_id": meta.get("budget_plan_id") or item.action_id if item.action_type in {"budget", "budget_plan"} else meta.get("budget_plan_id"),
                "template_family": meta.get("template_family"),
                "operator_family": meta.get("operator_family"),
                "mutation_type": meta.get("mutation_type"),
                "behavior_family": meta.get("behavior_family"),
                "candidate_source": meta.get("candidate_source"),
                "platform_sc_status": meta.get("platform_sc_status"),
            }
        )

    def context_fingerprint(self, features: dict[str, Any] | None, context: dict[str, Any] | None) -> dict[str, Any]:
        feats = features if isinstance(features, dict) else {}
        ctx = context if isinstance(context, dict) else {}
        merged = {**ctx, **feats}
        keys = {
            "decision_type",
            "experiment_id",
            "arm_id",
            "budget_plan_id",
            "template_family",
            "operator_family",
            "mutation_type",
            "behavior_family",
            "candidate_source",
            "platform_sc_status",
        }
        fp = {key: merged.get(key) for key in keys}
        fp["feature_keys"] = sorted(str(k) for k in feats.keys())
        fp["context_keys"] = sorted(str(k) for k in ctx.keys())
        return _compact(fp)

    def combined_fingerprint(self, request_or_record: Any) -> dict[str, Any]:
        if isinstance(request_or_record, CounterfactualRequest):
            req = CounterfactualRequest.from_dict(request_or_record)
            action_fp = self.action_fingerprint(req.target_action)
            context_fp = self.context_fingerprint(req.features, {**(req.context or {}), "decision_type": req.decision_type, "experiment_id": req.experiment_id, "arm_id": req.arm_id, "budget_plan_id": req.budget_plan_id})
            return _compact({**context_fp, **action_fp, "decision_type": req.decision_type})
        record = ReplayRecord.from_dict(request_or_record)
        action_fp = self.action_fingerprint(record.chosen_action)
        context_fp = self.context_fingerprint(record.features, {**(record.context or {}), "decision_type": record.decision_type, "experiment_id": record.experiment_id, "arm_id": record.arm_id, "budget_plan_id": record.budget_plan_id})
        return _compact({**context_fp, **action_fp, "decision_type": record.decision_type})

    def similarity(self, a: dict[str, Any], b: dict[str, Any]) -> float:
        left = a if isinstance(a, dict) else {}
        right = b if isinstance(b, dict) else {}
        if not left or not right:
            return 0.0
        score = 0.0
        total = 0.0
        weights = {
            "decision_type": 3.0,
            "action_type": 3.0,
            "action_id": 1.5,
            "action_source": 0.5,
            "experiment_id": 1.0,
            "arm_id": 1.0,
            "budget_plan_id": 1.0,
            "template_family": 0.8,
            "operator_family": 0.8,
            "mutation_type": 0.8,
            "behavior_family": 0.8,
            "candidate_source": 0.5,
            "platform_sc_status": 0.4,
        }
        for key, weight in weights.items():
            total += weight
            lv = left.get(key)
            rv = right.get(key)
            if lv is None or rv is None or lv == "" or rv == "":
                score += weight * 0.25
            elif str(lv) == str(rv):
                score += weight
        score += _jaccard(left.get("feature_keys"), right.get("feature_keys")) * 0.8
        score += _jaccard(left.get("context_keys"), right.get("context_keys")) * 0.8
        total += 1.6
        result = score / total if total else 0.0
        if left.get("decision_type") and right.get("decision_type") and str(left.get("decision_type")) != str(right.get("decision_type")):
            result *= 0.45
        if left.get("action_type") and right.get("action_type") and str(left.get("action_type")) != str(right.get("action_type")):
            result *= 0.50
        return max(0.0, min(1.0, float(result)))


def _jaccard(a: Any, b: Any) -> float:
    left = {str(x) for x in a} if isinstance(a, (list, tuple, set)) else set()
    right = {str(x) for x in b} if isinstance(b, (list, tuple, set)) else set()
    if not left and not right:
        return 0.25
    union = left | right
    return len(left & right) / len(union) if union else 0.0


def _compact(data: dict[str, Any]) -> dict[str, Any]:
    return {str(k): v for k, v in data.items() if v is not None and v != ""}
