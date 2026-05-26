from __future__ import annotations

import json
import re
from typing import Any

from .dashboard_schema import (
    DashboardMLStatus,
    DashboardObservabilityStatus,
    DashboardRuntimeStatus,
    DashboardSnapshot,
    DashboardSourceStatus,
    DashboardStrategyStatus,
)


class CLIStatusFormatter:
    def format_snapshot(self, snapshot: DashboardSnapshot, compact: bool = True, limit: int = 8) -> str:
        lines: list[str] = [f"WorldQuant final status @ {snapshot.generated_at}"]
        lines.append(self.format_runtime(snapshot.runtime))
        lines.append(self.format_ml(snapshot.ml))
        lines.append(self.format_strategy(snapshot.strategy))
        lines.append(self.format_observability(snapshot.observability))
        lines.append(self.format_sources(snapshot.sources))
        lines.append(self.format_recent_events(snapshot.runtime.recent_events, limit=limit if compact else max(limit, 20)))
        evidence_summary = getattr(snapshot.runtime, "legacy_evidence_summary", {}) or {}
        if evidence_summary:
            lines.append(self.format_legacy_evidence(evidence_summary, limit=3 if compact else limit))
        errors = snapshot.raw_payload.get("log_errors", []) if isinstance(snapshot.raw_payload, dict) else []
        if errors:
            lines.append(self.format_error_summary(errors, limit=3 if compact else limit))
        if snapshot.observability.recommended_human_checks:
            checks = "; ".join(self.truncate_text(item, 120) for item in snapshot.observability.recommended_human_checks[:3])
            lines.append(f"Human checks: {checks}")
        if snapshot.global_warnings:
            shown = snapshot.global_warnings[:5 if compact else limit]
            lines.append("Warnings: " + "; ".join(self.truncate_text(w, 120) for w in shown))
        return "\n".join(line for line in lines if line)

    def format_runtime(self, runtime: DashboardRuntimeStatus) -> str:
        return (
            "Runtime: "
            f"running={runtime.workflow_running} state={runtime.current_state or 'UNKNOWN'} "
            f"template={runtime.current_template or '-'} alpha={runtime.current_alpha_id or '-'} "
            f"iter={runtime.current_iteration if runtime.current_iteration is not None else '-'} "
            f"wait={runtime.platform_waiting} progress={_fmt(getattr(runtime, 'platform_progress', None))} "
            f"parse={runtime.parse_waiting} parse_status={getattr(runtime, 'parse_status', None) or '-'} "
            f"sc={runtime.sc_check_status or '-'} reward={_fmt(getattr(runtime, 'last_reward', None))} "
            f"sc_value={_fmt(getattr(runtime, 'last_sc_value', None))}"
        )

    def format_ml(self, ml: DashboardMLStatus) -> str:
        return (
            "ML: "
            f"enabled={ml.model_enabled} active={ml.active_model_id or '-'} models={_fmt(ml.model_count)} "
            f"train_samples={_fmt(ml.training_sample_count)} predictions={_fmt(ml.prediction_count)} "
            f"safety={ml.safety_gate_status or '-'}"
        )

    def format_strategy(self, strategy: DashboardStrategyStatus) -> str:
        return (
            "Strategy: "
            f"champion={strategy.champion or '-'} challenger={_fmt(strategy.challenger_count)} "
            f"limited={_fmt(strategy.limited_active_count)} shadow={_fmt(strategy.shadow_count)} "
            f"disabled={_fmt(strategy.disabled_count)} budget_total={_fmt(strategy.budget_total_ratio)} "
            f"high_risk={_fmt(strategy.high_risk_count)}"
        )

    def format_observability(self, observability: DashboardObservabilityStatus) -> str:
        findings = "; ".join(self.truncate_text(item, 100) for item in observability.key_findings[:3]) or "-"
        return (
            "Observability: "
            f"health={observability.overall_health or 'unknown'} metrics={observability.metrics_available} "
            f"alerts={observability.alert_count} critical={observability.critical_count} "
            f"warnings={observability.warning_count} explain={observability.explainability_available} "
            f"findings={findings}"
        )

    def format_sources(self, sources: list[DashboardSourceStatus]) -> str:
        unavailable = [s.source for s in sources if not s.available]
        stale = [s.source for s in sources if s.stale]
        return f"Sources: total={len(sources)} unavailable={len(unavailable)} stale={len(stale)} unavailable_names={','.join(unavailable[:5]) or '-'}"

    def format_recent_events(self, events: list[dict[str, Any]], limit: int = 8) -> str:
        if not events:
            return "Recent events: -"
        lines = ["Recent events:"]
        for event in events[-max(1, int(limit)) :]:
            lines.append(
                "  - "
                + " ".join(
                    part
                    for part in [
                        str(event.get("time") or ""),
                        str(event.get("level") or ""),
                        str(event.get("state") or ""),
                        f"alpha={event.get('alpha_id')}" if event.get("alpha_id") else "",
                        self.truncate_text(str(event.get("message") or ""), 160),
                    ]
                    if part
                )
            )
        return "\n".join(lines)

    def format_legacy_evidence(self, summary: dict[str, Any], limit: int = 3) -> str:
        if not summary:
            return ""
        parts = []
        for key, value in list(summary.items())[: max(1, int(limit))]:
            count = value.get("count") if isinstance(value, dict) else value
            parts.append(f"{key}={count}")
        return "Legacy evidence: " + "; ".join(parts)

    def format_error_summary(self, errors: list[dict[str, Any]], limit: int = 3) -> str:
        if not errors:
            return ""
        lines = ["Errors:"]
        for error in errors[-max(1, int(limit)) :]:
            message = self.truncate_text(str(error.get("message") or error), 180)
            lines.append(f"  - {error.get('time') or ''} {error.get('level') or 'ERROR'} {message}".strip())
        return "\n".join(lines)

    def truncate_text(self, text: str, max_chars: int = 240) -> str:
        value = re.sub(r"\s+", " ", str(text or "")).strip()
        if len(value) > max_chars:
            return value[: max(0, max_chars - 3)] + "..."
        return value

    def summarize_json(self, payload: dict[str, Any], max_keys: int = 12) -> dict[str, Any]:
        summary: dict[str, Any] = {}
        for key, value in list((payload or {}).items())[: max(1, int(max_keys))]:
            if isinstance(value, dict):
                summary[key] = {"type": "dict", "keys": list(value.keys())[:5]}
            elif isinstance(value, list):
                summary[key] = {"type": "list", "count": len(value)}
            else:
                summary[key] = self.truncate_text(str(value), 120)
        return summary


def snapshot_to_json(snapshot: DashboardSnapshot, *, indent: int | None = 2) -> str:
    return json.dumps(snapshot.to_dict(), ensure_ascii=False, indent=indent, default=str)


def _fmt(value: Any) -> str:
    return "-" if value is None else str(value)
