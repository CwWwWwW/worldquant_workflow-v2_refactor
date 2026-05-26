from __future__ import annotations

from typing import Any

from .alert_schema import AlertEvent, AlertRule, DriftSignal
from .schema import ObservabilityMetric, ObservabilitySourceStatus
from .utils import as_number, clean_list, utc_now_iso


class AlertRuleEngine:
    def __init__(self, *, config: Any | None = None, rules: list[AlertRule] | None = None) -> None:
        self.config = config
        self.rules = rules

    def default_rules(self) -> list[AlertRule]:
        warning_threshold = float(getattr(self.config, "observability_warning_count_threshold", 5) or 5)
        disk_threshold = float(getattr(self.config, "observability_disk_low_mb_threshold", 1024) or 1024)
        return [
            self._rule("alert_source_unavailable", "source_unavailable", "source_unavailable"),
            self._rule("alert_source_stale", "source_stale", "source_stale"),
            self._rule("alert_warning_count_high", "warning_count_high", "warning_count_high", threshold=warning_threshold),
            self._rule("alert_missing_status_file", "missing_status_file", "missing_status_file"),
            self._rule("alert_platform_failure_spike", "platform_failure_spike", "platform_failure_spike", source="platform"),
            self._rule("alert_parse_failure_spike", "parse_failure_spike", "parse_failure_spike", source="platform"),
            self._rule("alert_sc_risk_high", "sc_risk_high", "sc_risk_high", source="strategy", severity="warning"),
            self._rule("alert_model_failure_spike", "model_failure_spike", "model_failure_spike", source="ml"),
            self._rule("alert_governance_block_spike", "governance_block_spike", "governance_block_spike", source="governance"),
            self._rule("alert_strategy_budget_concentration", "strategy_budget_concentration", "strategy_budget_concentration", source="strategy_budget"),
            self._rule("alert_database_unavailable", "database_unavailable", "database_unavailable", source="database", severity="critical"),
            self._rule("alert_disk_low", "disk_low", "disk_low", source="system", threshold=disk_threshold, metric_name="system.free_disk_mb"),
        ]

    def evaluate(self, drift_signals: list[DriftSignal], source_statuses: list[ObservabilitySourceStatus], metrics: list[ObservabilityMetric]) -> list[AlertEvent]:
        safe_signals = [DriftSignal.from_dict(signal) for signal in list(drift_signals or [])]
        safe_statuses = [ObservabilitySourceStatus.from_dict(status) for status in list(source_statuses or [])]
        safe_metrics = [ObservabilityMetric.from_dict(metric) for metric in list(metrics or [])]
        alerts: list[AlertEvent] = []
        seen: set[tuple[str, str, str | None]] = set()
        for rule in self.rules or self.default_rules():
            event = self.evaluate_rule(AlertRule.from_dict(rule), safe_signals, safe_statuses, safe_metrics)
            if event is not None and event.triggered:
                key = (event.rule_id, event.source, event.metric_name)
                if key not in seen:
                    alerts.append(event)
                    seen.add(key)
        return alerts

    def evaluate_rule(self, rule: AlertRule, drift_signals: list[DriftSignal], source_statuses: list[ObservabilitySourceStatus], metrics: list[ObservabilityMetric]) -> AlertEvent | None:
        if not rule.enabled:
            return None
        condition = rule.condition_type
        if condition == "source_unavailable":
            for status in source_statuses:
                if not status.available:
                    return self.build_alert(rule, status.source, f"Source {status.source} is unavailable", reason_codes=["source_unavailable"])
        if condition == "source_stale":
            for status in source_statuses:
                if status.is_stale:
                    return self.build_alert(rule, status.source, f"Source {status.source} is stale", reason_codes=["source_stale"])
        if condition == "warning_count_high":
            count = sum(len(status.warnings or []) for status in source_statuses) + sum(1 for signal in drift_signals if signal.triggered and signal.severity == "warning")
            if count >= float(rule.threshold or 0):
                return self.build_alert(rule, "system", "Observability warning count is high", metric_name="observability.warning_count", metric_value=count, reason_codes=["warning_count_high"])
        if condition == "missing_status_file":
            for status in source_statuses:
                if status.status_path and any("missing" in str(w).lower() or "not_found" in str(w).lower() for w in status.warnings):
                    return self.build_alert(rule, status.source, f"Status file missing for {status.source}", reason_codes=["missing_status_file"])
        if condition == "database_unavailable":
            for status in source_statuses:
                if status.source == "database" and not status.available:
                    return self.build_alert(rule, "database", "Database observability source unavailable", reason_codes=["database_unavailable"])
        if condition == "disk_low":
            metric = self._latest_metric(metrics, rule.metric_name or "system.free_disk_mb")
            value = as_number(metric.value if metric else None, None)
            if value is not None and float(value) <= float(rule.threshold or 0):
                return self.build_alert(rule, "system", "Available disk space below advisory threshold", metric_name=metric.metric_name, metric_value=value, reason_codes=["disk_low"])
        matched = self._matching_drift_signal(rule, drift_signals)
        if matched is not None:
            return self.build_alert(
                rule,
                matched.source,
                f"{rule.alert_name} detected from drift signal",
                metric_name=matched.metric_name,
                metric_value=matched.current_value,
                reason_codes=list(matched.reason_codes or []) + [condition],
            )
        return None

    def build_alert(
        self,
        rule: AlertRule,
        source: str,
        message: str,
        metric_name: str | None = None,
        metric_value: int | float | str | bool | None = None,
        reason_codes: list[str] | None = None,
    ) -> AlertEvent:
        created_at = utc_now_iso()
        return AlertEvent(
            alert_id=f"alert:{rule.rule_id}:{source}:{created_at}",
            rule_id=rule.rule_id,
            alert_name=rule.alert_name or rule.condition_type,
            source=source or rule.source or "unknown",
            severity=rule.severity,
            status="open",
            message=message,
            triggered=True,
            created_at=created_at,
            metric_name=metric_name or rule.metric_name,
            metric_value=metric_value,
            reason_codes=[str(item) for item in clean_list(reason_codes or [rule.condition_type])],
            raw_payload={"condition_type": rule.condition_type, "mode": "advisory"},
        )

    def _rule(self, rule_id: str, alert_name: str, condition_type: str, *, source: str | None = None, metric_name: str | None = None, severity: str = "warning", threshold: float | None = None) -> AlertRule:
        return AlertRule(
            rule_id=rule_id,
            alert_name=alert_name,
            source=source,
            condition_type=condition_type,
            metric_name=metric_name,
            severity=severity,
            enabled=True,
            threshold=threshold,
            description=alert_name.replace("_", " "),
        )

    def _latest_metric(self, metrics: list[ObservabilityMetric], metric_name: str) -> ObservabilityMetric | None:
        selected = [ObservabilityMetric.from_dict(metric) for metric in metrics or [] if ObservabilityMetric.from_dict(metric).metric_name == metric_name]
        selected.sort(key=lambda item: item.timestamp or "")
        return selected[-1] if selected else None

    def _matching_drift_signal(self, rule: AlertRule, drift_signals: list[DriftSignal]) -> DriftSignal | None:
        condition = rule.condition_type
        for signal in drift_signals or []:
            item = DriftSignal.from_dict(signal)
            if not item.triggered:
                continue
            reasons = set(item.reason_codes or [])
            name = item.metric_name or ""
            if condition == "drift_signal_triggered":
                return item
            if condition == "platform_failure_spike" and ("platform_failure_spike" in reasons or "platform.failure" in name or "workflow.recent_failure_count" == name):
                return item
            if condition == "parse_failure_spike" and ("parse_failure_spike" in reasons or "parse_failure" in name):
                return item
            if condition == "sc_risk_high" and ("sc_risk_high" in reasons or "high_sc" in name or "sc_risk" in name):
                return item
            if condition == "model_failure_spike" and ("model_failure_spike" in reasons or "failed_prediction" in name):
                return item
            if condition == "governance_block_spike" and ("governance_block_spike" in reasons or "blocked_decision" in name):
                return item
            if condition == "strategy_budget_concentration" and ("strategy_budget_concentration" in reasons or "budget_max_ratio" in name or "budget_total_suggested_ratio" in name):
                return item
        return None
