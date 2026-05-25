from __future__ import annotations

from typing import Any

from .schema import ReplayComparison, ReplayPolicyDecision, ReplayPolicyMetrics


class ReplayMetricsCalculator:
    def __init__(self, *, min_observable_samples: int = 30) -> None:
        self.min_observable_samples = max(1, int(min_observable_samples or 30))

    def calculate_policy_metrics(self, replay_run_id: str, policy_decisions: list[ReplayPolicyDecision], decision_type: str | None = None) -> ReplayPolicyMetrics:
        decisions = [ReplayPolicyDecision.from_dict(item) for item in policy_decisions]
        if decision_type is not None:
            decisions = [item for item in decisions if (item.raw_payload or {}).get("decision_type") == decision_type]
        policy_name = decisions[0].policy_name if decisions else ""
        sample_count = len(decisions)
        observable = [item for item in decisions if item.observable_outcome]
        selected_count = sum(1 for item in decisions if item.selected_action is not None)
        actual_values = [item.selected_matches_actual for item in decisions if item.selected_matches_actual is not None]
        legacy_values = [item.selected_matches_legacy for item in decisions if item.selected_matches_legacy is not None]
        rewards = [float(item.reward) for item in observable if item.reward is not None]
        successes = [bool(item.success) for item in observable if item.success is not None]
        sc_values = [float(item.platform_sc_abs_max) for item in observable if item.platform_sc_abs_max is not None]
        quality_values = [bool(item.quality_passed) for item in observable if item.quality_passed is not None]
        reasons = sorted({str(reason) for item in decisions for reason in (item.reason_codes or [])})
        insufficient = sum(1 for item in decisions if "insufficient_counterfactual_evidence" in (item.reason_codes or []))
        return ReplayPolicyMetrics(
            replay_run_id=replay_run_id,
            policy_name=policy_name,
            decision_type=decision_type,
            sample_count=sample_count,
            observable_count=len(observable),
            coverage_rate=(len(observable) / sample_count) if sample_count else 0.0,
            agreement_with_actual_rate=_rate(actual_values),
            agreement_with_legacy_rate=_rate(legacy_values),
            avg_reward=_avg(rewards),
            success_rate=_rate(successes),
            avg_platform_sc_abs_max=_avg(sc_values),
            quality_pass_rate=_rate(quality_values),
            insufficient_evidence_count=insufficient,
            reason_codes=reasons,
            raw_payload={"selected_action_count": selected_count},
        )

    def compare_metrics(self, baseline_metrics: ReplayPolicyMetrics, challenger_metrics: ReplayPolicyMetrics) -> ReplayComparison:
        baseline = ReplayPolicyMetrics.from_dict(baseline_metrics)
        challenger = ReplayPolicyMetrics.from_dict(challenger_metrics)
        comparison = ReplayComparison(
            replay_run_id=challenger.replay_run_id or baseline.replay_run_id,
            baseline_policy=baseline.policy_name,
            challenger_policy=challenger.policy_name,
            decision_type=challenger.decision_type or baseline.decision_type,
            baseline_metrics=baseline.to_dict(),
            challenger_metrics=challenger.to_dict(),
            reward_delta=_delta(challenger.avg_reward, baseline.avg_reward),
            success_rate_delta=_delta(challenger.success_rate, baseline.success_rate),
            sc_risk_delta=_delta(challenger.avg_platform_sc_abs_max, baseline.avg_platform_sc_abs_max),
            quality_pass_delta=_delta(challenger.quality_pass_rate, baseline.quality_pass_rate),
        )
        comparison.confidence = self.confidence_from_samples(min(baseline.sample_count, challenger.sample_count), min(baseline.observable_count, challenger.observable_count))
        comparison.verdict = self.verdict_from_delta(comparison)
        return comparison

    def confidence_from_samples(self, sample_count: int, observable_count: int) -> str:
        observed = int(observable_count or 0)
        if observed < self.min_observable_samples or observed < 30:
            return "insufficient"
        if observed <= 100:
            return "low"
        if observed <= 500:
            return "medium"
        return "high"

    def verdict_from_delta(self, comparison: ReplayComparison | dict[str, Any]) -> str:
        item = ReplayComparison.from_dict(comparison)
        if item.confidence == "insufficient":
            return "insufficient_evidence"
        if item.reward_delta is None or item.success_rate_delta is None or item.sc_risk_delta is None:
            return "insufficient_evidence"
        quality_ok = item.quality_pass_delta is None or item.quality_pass_delta >= 0
        if item.reward_delta > 0 and item.success_rate_delta >= 0 and item.sc_risk_delta <= 0 and quality_ok:
            return "challenger_better"
        if item.reward_delta < 0 and item.success_rate_delta <= 0:
            return "challenger_worse"
        return "no_clear_difference"


def _avg(values: list[float]) -> float | None:
    return (sum(values) / len(values)) if values else None


def _rate(values: list[Any]) -> float | None:
    if not values:
        return None
    return sum(1 for item in values if bool(item)) / len(values)


def _delta(left: float | None, right: float | None) -> float | None:
    if left is None or right is None:
        return None
    return float(left) - float(right)
