from __future__ import annotations

import hashlib
from typing import Any

from .replay_metrics import ReplayMetricsCalculator
from .schema import ReplayComparison, ReplayPolicyMetrics, utc_now_iso


class BaselineComparator:
    def __init__(self, *, calculator: ReplayMetricsCalculator | None = None, baseline_policy: str = "legacy") -> None:
        self.calculator = calculator or ReplayMetricsCalculator()
        self.baseline_policy = baseline_policy or "legacy"

    def compare(self, replay_run_id: str, baseline_policy: str | None, challenger_policies: list[str] | None, metrics: list[ReplayPolicyMetrics]) -> list[ReplayComparison]:
        baseline_name = baseline_policy or self.baseline_policy
        challengers = set(challenger_policies or [])
        by_key: dict[tuple[str, str | None], ReplayPolicyMetrics] = {}
        for metric in metrics:
            item = ReplayPolicyMetrics.from_dict(metric)
            by_key[(item.policy_name, item.decision_type)] = item
        comparisons: list[ReplayComparison] = []
        for (policy_name, decision_type), metric in by_key.items():
            if policy_name == baseline_name:
                continue
            if challengers and policy_name not in challengers:
                continue
            baseline = by_key.get((baseline_name, decision_type))
            if baseline is None:
                continue
            comparison = self.compare_policy_pair(baseline, metric)
            comparison.replay_run_id = replay_run_id
            comparison.comparison_id = _comparison_id(comparison)
            comparisons.append(comparison)
        return comparisons

    def compare_policy_pair(self, baseline_metrics: ReplayPolicyMetrics | dict[str, Any], challenger_metrics: ReplayPolicyMetrics | dict[str, Any]) -> ReplayComparison:
        comparison = self.calculator.compare_metrics(ReplayPolicyMetrics.from_dict(baseline_metrics), ReplayPolicyMetrics.from_dict(challenger_metrics))
        if not comparison.comparison_id:
            comparison.comparison_id = _comparison_id(comparison)
        comparison.created_at = comparison.created_at or utc_now_iso()
        return comparison


def _comparison_id(comparison: ReplayComparison) -> str:
    seed = f"{comparison.replay_run_id}|{comparison.baseline_policy}|{comparison.challenger_policy}|{comparison.decision_type or ''}"
    return "replay_cmp:" + hashlib.sha256(seed.encode("utf-8", errors="replace")).hexdigest()[:24]
