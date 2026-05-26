from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .utils import clean_dict, clean_list, json_safe, utc_now_iso

EVIDENCE_SOURCES = {
    "workflow",
    "ml",
    "governance",
    "experiment",
    "decision_snapshot",
    "offline_replay",
    "counterfactual",
    "strategy_scoreboard",
    "strategy_portfolio",
    "strategy_budget",
    "observability_metrics",
    "observability_alerts",
    "health_diagnosis",
    "system",
    "unknown",
}
EVIDENCE_TYPES = {
    "actual_outcome",
    "decision_snapshot",
    "replay_metric",
    "counterfactual_estimate",
    "strategy_score",
    "strategy_state",
    "budget_allocation",
    "metric",
    "alert",
    "diagnosis",
    "governance_status",
    "experiment_summary",
    "system_status",
    "text",
}
CONFIDENCE_LEVELS = {"insufficient", "low", "medium", "high", "unknown"}
DECISION_TYPES = {
    "alpha_generation",
    "parent_selection",
    "mutation_policy",
    "strategy_selection",
    "budget_recommendation",
    "governance_decision",
    "replay_decision",
    "counterfactual_estimate",
    "workflow_run",
    "unknown",
}


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def _choice(value: Any, allowed: set[str], default: str) -> str:
    text = _text(value or default, default).strip()
    return text if text in allowed else default


def _bool(value: Any, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on", "enabled"}


def _list(value: Any) -> list[Any]:
    return clean_list(value if isinstance(value, list) else [])


def _dict(value: Any) -> dict[str, Any]:
    return clean_dict(value if isinstance(value, dict) else {})


@dataclass
class ExplanationEvidence:
    evidence_id: str = ""
    source: str = "unknown"
    evidence_type: str = "text"
    title: str = ""
    summary: str = ""
    confidence: str = "unknown"
    observed: bool = False
    estimated: bool = False
    advisory: bool = False
    timestamp: str = field(default_factory=utc_now_iso)
    related_ids: list[str] = field(default_factory=list)
    reason_codes: list[str] = field(default_factory=list)
    risk_flags: list[str] = field(default_factory=list)
    raw_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        source = _choice(self.source, EVIDENCE_SOURCES, "unknown")
        evidence_type = _choice(self.evidence_type, EVIDENCE_TYPES, "text")
        observed = _bool(self.observed)
        estimated = _bool(self.estimated)
        advisory = _bool(self.advisory)
        if evidence_type == "actual_outcome":
            observed = True
        if source == "counterfactual" or evidence_type == "counterfactual_estimate":
            estimated = True
            observed = False
            advisory = True
        if source == "offline_replay" or evidence_type == "replay_metric":
            advisory = True if not observed else advisory
        if source == "strategy_budget" or evidence_type == "budget_allocation":
            advisory = True
        if source in {"observability_alerts", "health_diagnosis"} or evidence_type in {"alert", "diagnosis"}:
            advisory = True
        data.update({
            "evidence_id": _text(self.evidence_id or f"evidence:{source}:{evidence_type}:{self.timestamp}"),
            "source": source,
            "evidence_type": evidence_type,
            "title": _text(self.title or evidence_type),
            "summary": _text(self.summary),
            "confidence": _choice(self.confidence, CONFIDENCE_LEVELS, "unknown"),
            "observed": observed,
            "estimated": estimated,
            "advisory": advisory,
            "timestamp": _text(self.timestamp or utc_now_iso()),
            "related_ids": [str(item) for item in _list(self.related_ids)],
            "reason_codes": [str(item) for item in _list(self.reason_codes)],
            "risk_flags": [str(item) for item in _list(self.risk_flags)],
            "raw_payload": _dict(self.raw_payload),
        })
        return clean_dict(data)

    @classmethod
    def from_dict(cls, data: Any) -> "ExplanationEvidence":
        source = data.to_dict() if isinstance(data, ExplanationEvidence) else (data if isinstance(data, dict) else {})
        return cls(
            evidence_id=_text(source.get("evidence_id") or source.get("id")),
            source=_choice(source.get("source"), EVIDENCE_SOURCES, "unknown"),
            evidence_type=_choice(source.get("evidence_type") or source.get("type"), EVIDENCE_TYPES, "text"),
            title=_text(source.get("title")),
            summary=_text(source.get("summary") or source.get("message")),
            confidence=_choice(source.get("confidence"), CONFIDENCE_LEVELS, "unknown"),
            observed=_bool(source.get("observed")),
            estimated=_bool(source.get("estimated")),
            advisory=_bool(source.get("advisory")),
            timestamp=_text(source.get("timestamp") or source.get("created_at") or source.get("updated_at") or utc_now_iso()),
            related_ids=[str(item) for item in _list(source.get("related_ids") or [])],
            reason_codes=[str(item) for item in _list(source.get("reason_codes") or [])],
            risk_flags=[str(item) for item in _list(source.get("risk_flags") or [])],
            raw_payload=_dict(source.get("raw_payload") or source),
        )


@dataclass
class DecisionTrace:
    trace_id: str = ""
    generated_at: str = field(default_factory=utc_now_iso)
    decision_id: str | None = None
    alpha_id: str | None = None
    run_id: str | None = None
    strategy_id: str | None = None
    decision_type: str = "unknown"
    decision_summary: str = ""
    selected_action: str | None = None
    alternative_actions: list[str] = field(default_factory=list)
    evidence: list[ExplanationEvidence] = field(default_factory=list)
    explanation: str = ""
    confidence: str = "unknown"
    warnings: list[str] = field(default_factory=list)
    raw_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        decision_type = _choice(self.decision_type, DECISION_TYPES, "unknown")
        generated_at = _text(self.generated_at or utc_now_iso())
        data.update({
            "trace_id": _text(self.trace_id or f"trace:{decision_type}:{self.decision_id or self.strategy_id or generated_at}"),
            "generated_at": generated_at,
            "decision_id": None if self.decision_id in {None, ""} else str(self.decision_id),
            "alpha_id": None if self.alpha_id in {None, ""} else str(self.alpha_id),
            "run_id": None if self.run_id in {None, ""} else str(self.run_id),
            "strategy_id": None if self.strategy_id in {None, ""} else str(self.strategy_id),
            "decision_type": decision_type,
            "decision_summary": _text(self.decision_summary),
            "selected_action": None if self.selected_action in {None, ""} else str(self.selected_action),
            "alternative_actions": [str(item) for item in _list(self.alternative_actions)],
            "evidence": [ExplanationEvidence.from_dict(item).to_dict() for item in list(self.evidence or [])],
            "explanation": _text(self.explanation),
            "confidence": _choice(self.confidence, CONFIDENCE_LEVELS, "unknown"),
            "warnings": [str(item) for item in _list(self.warnings)],
            "raw_payload": _dict(self.raw_payload),
        })
        return clean_dict(data)

    @classmethod
    def from_dict(cls, data: Any) -> "DecisionTrace":
        source = data.to_dict() if isinstance(data, DecisionTrace) else (data if isinstance(data, dict) else {})
        return cls(
            trace_id=_text(source.get("trace_id") or source.get("id")),
            generated_at=_text(source.get("generated_at") or utc_now_iso()),
            decision_id=None if source.get("decision_id") in {None, ""} else str(source.get("decision_id")),
            alpha_id=None if source.get("alpha_id") in {None, ""} else str(source.get("alpha_id")),
            run_id=None if source.get("run_id") in {None, ""} else str(source.get("run_id")),
            strategy_id=None if source.get("strategy_id") in {None, ""} else str(source.get("strategy_id")),
            decision_type=_choice(source.get("decision_type"), DECISION_TYPES, "unknown"),
            decision_summary=_text(source.get("decision_summary") or source.get("summary")),
            selected_action=None if source.get("selected_action") in {None, ""} else str(source.get("selected_action")),
            alternative_actions=[str(item) for item in _list(source.get("alternative_actions") or [])],
            evidence=[ExplanationEvidence.from_dict(item) for item in _list(source.get("evidence") or [])],
            explanation=_text(source.get("explanation")),
            confidence=_choice(source.get("confidence"), CONFIDENCE_LEVELS, "unknown"),
            warnings=[str(item) for item in _list(source.get("warnings") or [])],
            raw_payload=_dict(source.get("raw_payload") or {}),
        )


@dataclass
class RunExplanation:
    explanation_id: str = ""
    generated_at: str = field(default_factory=utc_now_iso)
    window_start: str | None = None
    window_end: str | None = None
    run_summary: str = ""
    key_findings: list[str] = field(default_factory=list)
    decision_traces: list[DecisionTrace] = field(default_factory=list)
    alerts_summary: dict[str, Any] = field(default_factory=dict)
    diagnosis_summary: dict[str, Any] = field(default_factory=dict)
    strategy_summary: dict[str, Any] = field(default_factory=dict)
    budget_summary: dict[str, Any] = field(default_factory=dict)
    evidence_summary: dict[str, Any] = field(default_factory=dict)
    limitations: list[str] = field(default_factory=list)
    recommended_human_checks: list[str] = field(default_factory=list)
    auto_action_allowed: bool = False
    raw_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        generated_at = _text(self.generated_at or utc_now_iso())
        return clean_dict({
            "explanation_id": _text(self.explanation_id or f"run_explanation:{generated_at}"),
            "generated_at": generated_at,
            "window_start": None if self.window_start in {None, ""} else str(self.window_start),
            "window_end": None if self.window_end in {None, ""} else str(self.window_end),
            "run_summary": _text(self.run_summary),
            "key_findings": [str(item) for item in _list(self.key_findings)],
            "decision_traces": [DecisionTrace.from_dict(item).to_dict() for item in list(self.decision_traces or [])],
            "alerts_summary": _dict(self.alerts_summary),
            "diagnosis_summary": _dict(self.diagnosis_summary),
            "strategy_summary": _dict(self.strategy_summary),
            "budget_summary": _dict(self.budget_summary),
            "evidence_summary": _dict(self.evidence_summary),
            "limitations": [str(item) for item in _list(self.limitations)],
            "recommended_human_checks": [str(item) for item in _list(self.recommended_human_checks)],
            "auto_action_allowed": False,
            "raw_payload": _dict(self.raw_payload),
        })

    @classmethod
    def from_dict(cls, data: Any) -> "RunExplanation":
        source = data.to_dict() if isinstance(data, RunExplanation) else (data if isinstance(data, dict) else {})
        return cls(
            explanation_id=_text(source.get("explanation_id") or source.get("id")),
            generated_at=_text(source.get("generated_at") or utc_now_iso()),
            window_start=None if source.get("window_start") in {None, ""} else str(source.get("window_start")),
            window_end=None if source.get("window_end") in {None, ""} else str(source.get("window_end")),
            run_summary=_text(source.get("run_summary")),
            key_findings=[str(item) for item in _list(source.get("key_findings") or [])],
            decision_traces=[DecisionTrace.from_dict(item) for item in _list(source.get("decision_traces") or [])],
            alerts_summary=_dict(source.get("alerts_summary") or {}),
            diagnosis_summary=_dict(source.get("diagnosis_summary") or {}),
            strategy_summary=_dict(source.get("strategy_summary") or {}),
            budget_summary=_dict(source.get("budget_summary") or {}),
            evidence_summary=_dict(source.get("evidence_summary") or {}),
            limitations=[str(item) for item in _list(source.get("limitations") or [])],
            recommended_human_checks=[str(item) for item in _list(source.get("recommended_human_checks") or [])],
            auto_action_allowed=False,
            raw_payload=_dict(source.get("raw_payload") or {}),
        )


@dataclass
class DailyRunReport:
    report_id: str = ""
    generated_at: str = field(default_factory=utc_now_iso)
    date: str = ""
    overall_summary: str = ""
    health_status: str = "unknown"
    key_metrics: dict[str, Any] = field(default_factory=dict)
    key_alerts: list[str] = field(default_factory=list)
    key_diagnoses: list[str] = field(default_factory=list)
    strategy_explanations: list[str] = field(default_factory=list)
    budget_explanations: list[str] = field(default_factory=list)
    offline_evidence_summary: dict[str, Any] = field(default_factory=dict)
    counterfactual_limitations: list[str] = field(default_factory=list)
    recommended_human_checks: list[str] = field(default_factory=list)
    auto_action_allowed: bool = False
    raw_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        generated_at = _text(self.generated_at or utc_now_iso())
        return clean_dict({
            "report_id": _text(self.report_id or f"daily_observability_report:{self.date or generated_at}"),
            "generated_at": generated_at,
            "date": _text(self.date or generated_at[:10]),
            "overall_summary": _text(self.overall_summary),
            "health_status": _text(self.health_status or "unknown", "unknown"),
            "key_metrics": _dict(self.key_metrics),
            "key_alerts": [str(item) for item in _list(self.key_alerts)],
            "key_diagnoses": [str(item) for item in _list(self.key_diagnoses)],
            "strategy_explanations": [str(item) for item in _list(self.strategy_explanations)],
            "budget_explanations": [str(item) for item in _list(self.budget_explanations)],
            "offline_evidence_summary": _dict(self.offline_evidence_summary),
            "counterfactual_limitations": [str(item) for item in _list(self.counterfactual_limitations)],
            "recommended_human_checks": [str(item) for item in _list(self.recommended_human_checks)],
            "auto_action_allowed": False,
            "raw_payload": _dict(self.raw_payload),
        })

    @classmethod
    def from_dict(cls, data: Any) -> "DailyRunReport":
        source = data.to_dict() if isinstance(data, DailyRunReport) else (data if isinstance(data, dict) else {})
        return cls(
            report_id=_text(source.get("report_id") or source.get("id")),
            generated_at=_text(source.get("generated_at") or utc_now_iso()),
            date=_text(source.get("date")),
            overall_summary=_text(source.get("overall_summary")),
            health_status=_text(source.get("health_status") or "unknown", "unknown"),
            key_metrics=_dict(source.get("key_metrics") or {}),
            key_alerts=[str(item) for item in _list(source.get("key_alerts") or [])],
            key_diagnoses=[str(item) for item in _list(source.get("key_diagnoses") or [])],
            strategy_explanations=[str(item) for item in _list(source.get("strategy_explanations") or [])],
            budget_explanations=[str(item) for item in _list(source.get("budget_explanations") or [])],
            offline_evidence_summary=_dict(source.get("offline_evidence_summary") or {}),
            counterfactual_limitations=[str(item) for item in _list(source.get("counterfactual_limitations") or [])],
            recommended_human_checks=[str(item) for item in _list(source.get("recommended_human_checks") or [])],
            auto_action_allowed=False,
            raw_payload=_dict(source.get("raw_payload") or {}),
        )


@dataclass
class StageSummaryReport:
    report_id: str = ""
    generated_at: str = field(default_factory=utc_now_iso)
    stage_name: str = "phase7-observability"
    summary: str = ""
    completed_substages: list[str] = field(default_factory=list)
    generated_reports: list[str] = field(default_factory=list)
    key_capabilities: list[str] = field(default_factory=list)
    known_limitations: list[str] = field(default_factory=list)
    next_stage_recommendations: list[str] = field(default_factory=list)
    auto_action_allowed: bool = False
    raw_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        generated_at = _text(self.generated_at or utc_now_iso())
        return clean_dict({
            "report_id": _text(self.report_id or f"stage7_summary_report:{generated_at}"),
            "generated_at": generated_at,
            "stage_name": _text(self.stage_name or "phase7-observability", "phase7-observability"),
            "summary": _text(self.summary),
            "completed_substages": [str(item) for item in _list(self.completed_substages)],
            "generated_reports": [str(item) for item in _list(self.generated_reports)],
            "key_capabilities": [str(item) for item in _list(self.key_capabilities)],
            "known_limitations": [str(item) for item in _list(self.known_limitations)],
            "next_stage_recommendations": [str(item) for item in _list(self.next_stage_recommendations)],
            "auto_action_allowed": False,
            "raw_payload": _dict(self.raw_payload),
        })

    @classmethod
    def from_dict(cls, data: Any) -> "StageSummaryReport":
        source = data.to_dict() if isinstance(data, StageSummaryReport) else (data if isinstance(data, dict) else {})
        return cls(
            report_id=_text(source.get("report_id") or source.get("id")),
            generated_at=_text(source.get("generated_at") or utc_now_iso()),
            stage_name=_text(source.get("stage_name") or "phase7-observability", "phase7-observability"),
            summary=_text(source.get("summary")),
            completed_substages=[str(item) for item in _list(source.get("completed_substages") or [])],
            generated_reports=[str(item) for item in _list(source.get("generated_reports") or [])],
            key_capabilities=[str(item) for item in _list(source.get("key_capabilities") or [])],
            known_limitations=[str(item) for item in _list(source.get("known_limitations") or [])],
            next_stage_recommendations=[str(item) for item in _list(source.get("next_stage_recommendations") or [])],
            auto_action_allowed=False,
            raw_payload=_dict(source.get("raw_payload") or {}),
        )
