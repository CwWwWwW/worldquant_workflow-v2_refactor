from __future__ import annotations

from collections import defaultdict
from typing import Any

from .explanation_schema import DecisionTrace, ExplanationEvidence
from .utils import utc_now_iso


class DecisionTraceBuilder:
    def build_traces(self, evidence: list[ExplanationEvidence]) -> list[DecisionTrace]:
        safe_evidence = [ExplanationEvidence.from_dict(item) for item in list(evidence or [])]
        traces: list[DecisionTrace] = []
        for builder in (
            self.build_strategy_trace,
            self.build_budget_trace,
            self.build_governance_trace,
            self.build_offline_trace,
            self.build_counterfactual_trace,
            self.build_workflow_trace,
        ):
            trace = builder(safe_evidence)
            if isinstance(trace, list):
                traces.extend(trace)
            elif trace is not None:
                traces.append(trace)
        return traces

    def build_strategy_trace(self, evidence: list[ExplanationEvidence]) -> DecisionTrace | None:
        items = [item for item in evidence if item.source in {"strategy_scoreboard", "strategy_portfolio"} or item.evidence_type in {"strategy_score", "strategy_state"}]
        return self._generic_trace("strategy_selection", "Strategy selection/state evidence is advisory and based on available score and portfolio reports.", items, selected_action=self._selected_strategy(items))

    def build_budget_trace(self, evidence: list[ExplanationEvidence]) -> DecisionTrace | None:
        items = [item for item in evidence if item.source == "strategy_budget" or item.evidence_type == "budget_allocation"]
        trace = self._generic_trace("budget_recommendation", "Strategy budget evidence is advisory only and was not applied by explainability.", items)
        if trace:
            trace.warnings.append("strategy budget evidence is advisory only")
        return trace

    def build_governance_trace(self, evidence: list[ExplanationEvidence]) -> DecisionTrace | None:
        items = [item for item in evidence if item.source == "governance" or item.evidence_type == "governance_status"]
        trace = self._generic_trace("governance_decision", "Governance evidence is summarized for human review only.", items)
        if trace and any("block" in self._text(item).lower() for item in items):
            trace.warnings.append("governance block evidence requires human review")
        return trace

    def build_offline_trace(self, evidence: list[ExplanationEvidence]) -> DecisionTrace | None:
        items = [item for item in evidence if item.source in {"decision_snapshot", "offline_replay"} or item.evidence_type in {"decision_snapshot", "replay_metric", "actual_outcome"}]
        trace = self._generic_trace("replay_decision", "Offline replay and decision snapshot evidence are summarized without changing workflow decisions.", items)
        if trace:
            trace.warnings.append("replay metrics remain advisory unless backed by actual outcomes")
        return trace

    def build_counterfactual_trace(self, evidence: list[ExplanationEvidence]) -> DecisionTrace | None:
        items = [item for item in evidence if item.source == "counterfactual" or item.evidence_type == "counterfactual_estimate"]
        trace = self._generic_trace("counterfactual_estimate", "Counterfactual evidence is estimated and not an observed outcome.", items)
        if trace:
            trace.warnings.append("counterfactual estimates are not observed outcomes")
        return trace

    def build_workflow_trace(self, evidence: list[ExplanationEvidence]) -> DecisionTrace | None:
        items = [item for item in evidence if item.source in {"workflow", "observability_metrics", "observability_alerts", "health_diagnosis", "system"} or item.evidence_type in {"metric", "alert", "diagnosis", "system_status"}]
        return self._generic_trace("workflow_run", "Workflow health and observability evidence are summarized for this run window.", items)

    def summarize_trace(self, trace: DecisionTrace) -> str:
        data = DecisionTrace.from_dict(trace).to_dict()
        return f"{data['decision_type']}: {data.get('decision_summary') or data.get('explanation')}; evidence_count={len(data.get('evidence') or [])}"

    def _generic_trace(self, decision_type: str, summary: str, items: list[ExplanationEvidence], *, selected_action: str | None = None) -> DecisionTrace | None:
        if not items:
            return None
        generated_at = utc_now_iso()
        grouped = self._group_related(items)
        evidence = []
        for group_items in grouped.values():
            evidence.extend(group_items[:25])
        confidence = self._confidence(evidence)
        trace = DecisionTrace(
            trace_id=f"trace:{decision_type}:{generated_at}",
            generated_at=generated_at,
            decision_type=decision_type,
            decision_summary=summary,
            selected_action=selected_action,
            alternative_actions=[],
            evidence=evidence[:100],
            explanation=f"{summary} Evidence count: {len(items)}.",
            confidence=confidence,
            warnings=[],
            raw_payload={"evidence_count": len(items), "group_count": len(grouped), "mode": "explain_only"},
        )
        if any(item.estimated for item in evidence):
            trace.warnings.append("contains estimated evidence")
        if any(item.advisory for item in evidence):
            trace.warnings.append("contains advisory evidence")
        return trace

    def _group_related(self, items: list[ExplanationEvidence]) -> dict[str, list[ExplanationEvidence]]:
        grouped: dict[str, list[ExplanationEvidence]] = defaultdict(list)
        for item in items:
            data = item.to_dict()
            key = ":".join([data.get("source", "unknown"), data.get("evidence_type", "text"), ",".join(data.get("related_ids") or [])])
            grouped[key].append(ExplanationEvidence.from_dict(data))
        return grouped

    def _confidence(self, items: list[ExplanationEvidence]) -> str:
        values = [ExplanationEvidence.from_dict(item).confidence for item in items]
        if "high" in values:
            return "high"
        if "medium" in values:
            return "medium"
        if values:
            return values[0]
        return "insufficient"

    def _selected_strategy(self, items: list[ExplanationEvidence]) -> str | None:
        for item in items:
            payload = item.raw_payload or {}
            if payload.get("champion_strategy_id"):
                return str(payload.get("champion_strategy_id"))
            if payload.get("recommendation"):
                return str(payload.get("recommendation"))
        return None

    def _text(self, item: ExplanationEvidence) -> str:
        data = item.to_dict()
        return " ".join(str(data.get(key) or "") for key in ("title", "summary", "reason_codes", "risk_flags"))
