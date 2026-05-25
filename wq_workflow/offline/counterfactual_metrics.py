from __future__ import annotations

import hashlib
from typing import Any

from wq_workflow.data.json_utils import safe_float

from .schema import CounterfactualEstimate, CounterfactualEvidence, CounterfactualRequest, DecisionAction, utc_now_iso


class CounterfactualMetricsCalculator:
    def __init__(
        self,
        *,
        min_evidence: int = 30,
        min_effective_evidence: int = 15,
        high_sc_abs_max_threshold: float = 0.70,
        low_success_rate_threshold: float = 0.02,
        medium_confidence_evidence: int = 100,
        high_confidence_evidence: int = 500,
    ) -> None:
        self.min_evidence = int(min_evidence or 30)
        self.min_effective_evidence = int(min_effective_evidence or 15)
        self.high_sc_abs_max_threshold = float(high_sc_abs_max_threshold if high_sc_abs_max_threshold is not None else 0.70)
        self.low_success_rate_threshold = float(low_success_rate_threshold if low_success_rate_threshold is not None else 0.02)
        self.medium_confidence_evidence = int(medium_confidence_evidence or 100)
        self.high_confidence_evidence = int(high_confidence_evidence or 500)

    @classmethod
    def from_config(cls, config: Any | None = None) -> "CounterfactualMetricsCalculator":
        return cls(
            min_evidence=int(getattr(config, "counterfactual_min_evidence", 30) or 30),
            min_effective_evidence=int(getattr(config, "counterfactual_min_effective_evidence", 15) or 15),
            high_sc_abs_max_threshold=float(getattr(config, "counterfactual_high_sc_abs_max_threshold", 0.70) or 0.70),
            low_success_rate_threshold=float(getattr(config, "counterfactual_low_success_rate_threshold", 0.02) or 0.02),
            medium_confidence_evidence=int(getattr(config, "counterfactual_medium_confidence_evidence", 100) or 100),
            high_confidence_evidence=int(getattr(config, "counterfactual_high_confidence_evidence", 500) or 500),
        )

    def estimate_from_evidence(self, request: CounterfactualRequest | dict[str, Any], evidence_list: list[CounterfactualEvidence] | None) -> CounterfactualEstimate:
        req = CounterfactualRequest.from_dict(request)
        evidence = [CounterfactualEvidence.from_dict(item) for item in (evidence_list or [])]
        evidence_count = len(evidence)
        effective = int(sum(max(0.0, min(1.0, item.similarity_score)) for item in evidence))
        avg_similarity = (sum(item.similarity_score for item in evidence) / evidence_count) if evidence_count else 0.0
        min_evidence = max(1, int(req.min_evidence or self.min_evidence))
        target_json = DecisionAction.from_dict(req.target_action).to_dict() if req.target_action is not None else None
        estimate = CounterfactualEstimate(
            estimate_id=_estimate_id(req.request_id, req.decision_id, target_json or {}),
            request_id=req.request_id,
            decision_id=req.decision_id,
            target_action_json=target_json,
            evidence_count=evidence_count,
            effective_evidence_count=effective,
            confidence="insufficient",
            verdict="insufficient_evidence",
            estimated_not_observed=True,
            created_at=utc_now_iso(),
            raw_payload={"avg_similarity": avg_similarity, "min_evidence": min_evidence, "min_effective_evidence": self.min_effective_evidence},
        )
        if evidence_count < min_evidence or effective < self.min_effective_evidence:
            estimate.reason_codes = ["insufficient_evidence", "estimated_not_observed"]
            return estimate
        estimate.estimated_reward = _weighted_mean(evidence, "reward")
        estimate.estimated_success_rate = _weighted_bool_mean(evidence, "success")
        estimate.estimated_platform_sc_abs_max = _weighted_mean(evidence, "platform_sc_abs_max")
        estimate.estimated_quality_pass_rate = _weighted_bool_mean(evidence, "quality_passed")
        estimate.confidence = self.confidence_from_evidence(evidence_count, effective, avg_similarity)
        estimate.risk_flags = self.risk_flags_from_estimate(estimate)
        estimate.verdict = self.verdict_from_estimate(estimate, baseline_context={**(req.context or {}), **(req.raw_payload or {})})
        estimate.reason_codes = ["estimated_not_observed", "nearest_neighbor_estimate"]
        if estimate.risk_flags:
            estimate.reason_codes.extend(estimate.risk_flags)
        return CounterfactualEstimate.from_dict(estimate)

    def confidence_from_evidence(self, evidence_count: int, effective_evidence_count: int, avg_similarity: float) -> str:
        if evidence_count < self.min_evidence or effective_evidence_count < self.min_effective_evidence:
            return "insufficient"
        if avg_similarity < 0.60:
            return "low"
        if evidence_count >= self.high_confidence_evidence and avg_similarity >= 0.75:
            return "high"
        if evidence_count >= self.medium_confidence_evidence and avg_similarity >= 0.65:
            return "medium"
        return "low"

    def risk_flags_from_estimate(self, estimate: CounterfactualEstimate | dict[str, Any]) -> list[str]:
        item = CounterfactualEstimate.from_dict(estimate)
        flags: list[str] = []
        if item.estimated_platform_sc_abs_max is not None and item.estimated_platform_sc_abs_max > self.high_sc_abs_max_threshold:
            flags.append("high_sc_risk")
        if item.estimated_success_rate is not None and item.estimated_success_rate < self.low_success_rate_threshold:
            flags.append("low_success_estimate")
        return flags

    def verdict_from_estimate(self, estimate: CounterfactualEstimate | dict[str, Any], baseline_context: dict[str, Any] | None = None) -> str:
        item = CounterfactualEstimate.from_dict(estimate)
        if item.confidence == "insufficient":
            return "insufficient_evidence"
        if "high_sc_risk" in set(item.risk_flags or []):
            return "high_risk_estimate"
        baseline = baseline_context if isinstance(baseline_context, dict) else {}
        baseline_reward = safe_float(baseline.get("actual_reward", baseline.get("baseline_reward", baseline.get("reward"))), None)
        if baseline_reward is None or item.estimated_reward is None:
            return "no_clear_difference"
        delta = item.estimated_reward - baseline_reward
        if delta > 0.01 and "low_success_estimate" not in set(item.risk_flags or []):
            return "likely_better"
        if delta < -0.01:
            return "likely_worse"
        return "no_clear_difference"


def _weighted_mean(evidence: list[CounterfactualEvidence], attr: str) -> float | None:
    pairs = [(max(0.000001, item.similarity_score), safe_float(getattr(item, attr), None)) for item in evidence]
    pairs = [(w, v) for w, v in pairs if v is not None]
    total = sum(w for w, _ in pairs)
    return (sum(w * v for w, v in pairs) / total) if total else None


def _weighted_bool_mean(evidence: list[CounterfactualEvidence], attr: str) -> float | None:
    pairs = [(max(0.000001, item.similarity_score), getattr(item, attr)) for item in evidence if getattr(item, attr) is not None]
    total = sum(w for w, _ in pairs)
    return (sum(w * (1.0 if bool(v) else 0.0) for w, v in pairs) / total) if total else None


def _estimate_id(request_id: str, decision_id: str, action: dict[str, Any]) -> str:
    seed = f"{request_id}|{decision_id}|{action}"
    return "counterfactual_estimate:" + hashlib.sha256(seed.encode("utf-8", errors="replace")).hexdigest()[:24]
