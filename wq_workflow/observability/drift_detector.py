from __future__ import annotations

from typing import Any

from .alert_schema import DriftRule, DriftSignal
from .schema import ObservabilityMetric, ObservabilitySourceStatus
from .utils import as_number, clean_list, utc_now_iso


class DriftDetector:
    def __init__(self, *, config: Any | None = None, rules: list[DriftRule] | None = None) -> None:
        self.config = config
        self.rules = rules

    def default_rules(self) -> list[DriftRule]:
        window = int(getattr(self.config, "observability_drift_window_size", 20) or 20)
        baseline = int(getattr(self.config, "observability_drift_baseline_window_size", 100) or 100)
        failure_threshold = float(getattr(self.config, "observability_failure_spike_threshold", 0.5) or 0.5)
        success_threshold = float(getattr(self.config, "observability_success_drop_threshold", 0.3) or 0.3)
        sc_threshold = float(getattr(self.config, "observability_sc_risk_threshold", 0.7) or 0.7)
        return [
            self._rule("workflow_recent_failure_spike", "workflow.recent_failure_count", "workflow", "spike", failure_threshold, "increase", "warning", window, baseline),
            self._rule("workflow_success_drop", "workflow.recent_success_count", "workflow", "drop", success_threshold, "decrease", "warning", window, baseline),
            self._rule("platform_failure_spike", "platform.failure_count", "platform", "spike", failure_threshold, "increase", "warning", window, baseline, fallback_metric="workflow.recent_failure_count"),
            self._rule("parse_failure_spike", "platform.parse_failure_count", "platform", "spike", failure_threshold, "increase", "warning", window, baseline, fallback_metric="workflow.parse_failure_count"),
            self._rule("sc_risk_high", "strategy.high_sc_risk_count", "strategy", "absolute_threshold", sc_threshold, "increase", "critical", window, baseline, fallback_metric="strategy_budget.high_sc_cap_count"),
            self._rule("governance_block_spike", "governance.blocked_decision_count", "governance", "spike", failure_threshold, "increase", "warning", window, baseline),
            self._rule("model_failure_spike", "ml.failed_prediction_count", "ml", "spike", failure_threshold, "increase", "warning", window, baseline),
            self._rule("strategy_budget_concentration", "strategy.budget_max_ratio", "strategy_budget", "absolute_threshold", 0.7, "increase", "warning", window, baseline, fallback_metric="strategy.budget_total_suggested_ratio"),
            self._rule("source_stale", "*", None, "stale_source", 1.0, "both", "warning", window, baseline),
            self._rule("source_unavailable", "*", None, "missing_metric", 1.0, "both", "warning", window, baseline),
        ]

    def detect(self, metrics: list[ObservabilityMetric], source_statuses: list[ObservabilitySourceStatus]) -> list[DriftSignal]:
        safe_metrics = [ObservabilityMetric.from_dict(metric) for metric in list(metrics or [])]
        safe_statuses = [ObservabilitySourceStatus.from_dict(status) for status in list(source_statuses or [])]
        signals: list[DriftSignal] = []
        for rule in self.rules or self.default_rules():
            rule = DriftRule.from_dict(rule)
            if not rule.enabled:
                continue
            if rule.rule_type == "stale_source":
                signals.extend(self._detect_stale_sources(rule, safe_statuses))
                continue
            if rule.rule_type == "missing_metric" and rule.metric_name == "*":
                signals.extend(self._detect_unavailable_sources(rule, safe_statuses))
                continue
            signal = self.detect_for_rule(rule, safe_metrics)
            if signal is not None:
                signals.append(signal)
        return signals

    def detect_for_rule(self, rule: DriftRule, metrics: list[ObservabilityMetric]) -> DriftSignal | None:
        rule = DriftRule.from_dict(rule)
        if not rule.enabled:
            return None
        metric_names = [rule.metric_name]
        fallback = rule.raw_payload.get("fallback_metric")
        if fallback:
            metric_names.append(str(fallback))
        selected = self._select_metrics(metrics, metric_names, rule.source)
        source = rule.source or "unknown"
        metric_name = rule.metric_name
        if selected:
            source = selected[-1].source or source
            metric_name = selected[-1].metric_name or metric_name
        if not selected:
            return self._signal(
                rule,
                source=source,
                metric_name=metric_name,
                current=None,
                baseline=None,
                triggered=False,
                reason_codes=["metric_missing"],
            )
        values = [number for number in (self.safe_numeric(metric.value) for metric in selected) if number is not None]
        if not values:
            return self._signal(rule, source=source, metric_name=metric_name, current=None, baseline=None, triggered=False, reason_codes=["metric_non_numeric"])
        if len(values) <= max(1, rule.window_size) and len(values) > 1:
            current_values = values[-1:]
            baseline_values = values[:-1]
        else:
            current_values = values[-max(1, rule.window_size):]
            baseline_values = values[: -max(1, rule.window_size)]
        if not baseline_values:
            baseline_values = values[:-1]
        current = self.compute_current(current_values)
        baseline = self.compute_baseline(baseline_values)
        if current is None:
            return self._signal(rule, source=source, metric_name=metric_name, current=None, baseline=baseline, triggered=False, reason_codes=["data_insufficient"])
        if baseline is None:
            baseline = current
        delta = current - baseline
        denominator = abs(baseline) if abs(baseline) > 1e-12 else 1.0
        delta_ratio = delta / denominator
        triggered = self._is_triggered(rule, current, baseline, delta, delta_ratio)
        reason_codes = [rule.rule_id]
        if triggered:
            reason_codes.append(rule.rule_type)
        elif len(values) < 2:
            reason_codes.append("data_insufficient")
        return self._signal(rule, source=source, metric_name=metric_name, current=current, baseline=baseline, delta=delta, delta_ratio=delta_ratio, triggered=triggered, reason_codes=reason_codes)

    def compute_baseline(self, values: list[float]) -> float | None:
        clean = [float(value) for value in values or []]
        if not clean:
            return None
        return sum(clean) / len(clean)

    def compute_current(self, values: list[float]) -> float | None:
        clean = [float(value) for value in values or []]
        if not clean:
            return None
        return sum(clean) / len(clean)

    def safe_numeric(self, value: Any) -> float | None:
        number = as_number(value, None)
        return None if number is None else float(number)

    def _rule(self, rule_id: str, metric_name: str, source: str | None, rule_type: str, threshold: float, direction: str, severity: str, window: int, baseline: int, *, fallback_metric: str | None = None) -> DriftRule:
        raw_payload = {"fallback_metric": fallback_metric} if fallback_metric else {}
        return DriftRule(
            rule_id=rule_id,
            metric_name=metric_name,
            source=source,
            rule_type=rule_type,
            window_size=window,
            baseline_window_size=baseline,
            threshold=threshold,
            direction=direction,
            severity=severity,
            enabled=True,
            description=rule_id.replace("_", " "),
            raw_payload=raw_payload,
        )

    def _select_metrics(self, metrics: list[ObservabilityMetric], metric_names: list[str], source: str | None) -> list[ObservabilityMetric]:
        names = {name for name in metric_names if name and name != "*"}
        selected: list[ObservabilityMetric] = []
        for metric in metrics or []:
            item = ObservabilityMetric.from_dict(metric)
            if item.metric_name not in names:
                continue
            if source and item.source != source and not item.metric_name.startswith(f"{source}."):
                fallback = any(item.metric_name == name for name in metric_names[1:])
                if not fallback:
                    continue
            selected.append(item)
        selected.sort(key=lambda item: item.timestamp or "")
        return selected[-max(1, int(getattr(self.config, "observability_drift_baseline_window_size", 100) or 100) + int(getattr(self.config, "observability_drift_window_size", 20) or 20)):]

    def _is_triggered(self, rule: DriftRule, current: float, baseline: float, delta: float, delta_ratio: float) -> bool:
        threshold = float(rule.threshold or 0.0)
        if rule.rule_type in {"absolute_threshold", "ratio_out_of_range"}:
            if rule.direction == "decrease":
                return current <= threshold
            return current >= threshold
        if rule.rule_type in {"spike", "relative_change", "moving_average_shift"}:
            if rule.direction == "decrease":
                return -delta_ratio >= threshold
            if rule.direction == "increase":
                return delta_ratio >= threshold
            return abs(delta_ratio) >= threshold
        if rule.rule_type == "drop":
            return -delta_ratio >= threshold
        return False

    def _detect_stale_sources(self, rule: DriftRule, statuses: list[ObservabilitySourceStatus]) -> list[DriftSignal]:
        signals: list[DriftSignal] = []
        for status in statuses or []:
            item = ObservabilitySourceStatus.from_dict(status)
            if item.is_stale:
                signals.append(self._signal(rule, source=item.source, metric_name=f"{item.source}.source_stale", current=True, baseline=False, delta=None, delta_ratio=None, triggered=True, reason_codes=["source_stale"]))
        return signals

    def _detect_unavailable_sources(self, rule: DriftRule, statuses: list[ObservabilitySourceStatus]) -> list[DriftSignal]:
        signals: list[DriftSignal] = []
        for status in statuses or []:
            item = ObservabilitySourceStatus.from_dict(status)
            if not item.available:
                signals.append(self._signal(rule, source=item.source, metric_name=f"{item.source}.source_available", current=False, baseline=True, delta=None, delta_ratio=None, triggered=True, reason_codes=["source_unavailable"]))
        return signals

    def _signal(
        self,
        rule: DriftRule,
        *,
        source: str,
        metric_name: str,
        current: Any,
        baseline: Any,
        triggered: bool,
        reason_codes: list[str],
        delta: float | None = None,
        delta_ratio: float | None = None,
    ) -> DriftSignal:
        created_at = utc_now_iso()
        return DriftSignal(
            signal_id=f"drift_signal:{rule.rule_id}:{source}:{metric_name}:{created_at}",
            rule_id=rule.rule_id,
            source=source or "unknown",
            metric_name=metric_name or rule.metric_name,
            current_value=current,
            baseline_value=baseline,
            delta=delta,
            delta_ratio=delta_ratio,
            threshold=rule.threshold,
            triggered=triggered,
            severity=rule.severity,
            reason_codes=[str(item) for item in clean_list(reason_codes)],
            created_at=created_at,
            raw_payload={"rule_type": rule.rule_type, "direction": rule.direction},
        )
