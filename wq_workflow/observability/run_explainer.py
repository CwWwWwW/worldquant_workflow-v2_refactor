from __future__ import annotations

from collections import Counter
from typing import Any

from .explanation_schema import DecisionTrace, ExplanationEvidence, RunExplanation
from .utils import utc_now_iso


class RunExplainer:
    def explain(self, evidence: list[ExplanationEvidence], traces: list[DecisionTrace]) -> RunExplanation:
        safe_evidence = [ExplanationEvidence.from_dict(item) for item in list(evidence or [])]
        safe_traces = [DecisionTrace.from_dict(item) for item in list(traces or [])]
        generated_at = utc_now_iso()
        return RunExplanation(
            explanation_id=f"run_explanation:{generated_at}",
            generated_at=generated_at,
            window_start=self._min_time(safe_evidence),
            window_end=self._max_time(safe_evidence),
            run_summary=self.summarize_run(safe_evidence, safe_traces),
            key_findings=self.build_key_findings(safe_evidence, safe_traces),
            decision_traces=safe_traces,
            alerts_summary=self.summarize_alerts(safe_evidence),
            diagnosis_summary=self.summarize_diagnosis(safe_evidence),
            strategy_summary=self.summarize_strategy(safe_evidence),
            budget_summary=self.summarize_budget(safe_evidence),
            evidence_summary=self.summarize_evidence(safe_evidence),
            limitations=self.build_limitations(safe_evidence),
            recommended_human_checks=self.build_human_checks(safe_evidence, safe_traces),
            auto_action_allowed=False,
            raw_payload={"mode": "explain_only", "evidence_count": len(safe_evidence), "trace_count": len(safe_traces)},
        )

    def summarize_run(self, evidence: list[ExplanationEvidence], traces: list[DecisionTrace]) -> str:
        if not evidence:
            return "Evidence insufficient: no explanation evidence was available for this window."
        counts = Counter(item.source for item in evidence)
        return f"Explain-only run summary built from {len(evidence)} evidence item(s) across {len(counts)} source(s) and {len(traces)} decision trace(s)."

    def build_key_findings(self, evidence: list[ExplanationEvidence], traces: list[DecisionTrace]) -> list[str]:
        findings: list[str] = []
        for item in evidence:
            data = item.to_dict()
            text = self._text(data)
            if data.get("evidence_type") == "diagnosis" and ("critical" in text.lower() or data.get("raw_payload", {}).get("status") == "critical"):
                findings.append(f"critical diagnosis: {data.get('title')}: {data.get('summary')}")
        if any(item.source == "strategy_budget" for item in evidence):
            findings.append("strategy budget recommendations are advisory only and were not applied")
        if any(item.source == "counterfactual" for item in evidence):
            findings.append("counterfactual evidence is estimated, not observed")
        if not findings and not evidence:
            findings.append("evidence insufficient")
        return self._dedupe(findings)

    def summarize_alerts(self, evidence: list[ExplanationEvidence]) -> dict[str, Any]:
        alerts = [item.to_dict() for item in evidence if item.evidence_type == "alert" or item.source == "observability_alerts"]
        return {"alert_count": len(alerts), "critical_count": self._count_text(alerts, "critical"), "warning_count": self._count_text(alerts, "warning")}

    def summarize_diagnosis(self, evidence: list[ExplanationEvidence]) -> dict[str, Any]:
        diagnoses = [item.to_dict() for item in evidence if item.evidence_type == "diagnosis" or item.source == "health_diagnosis"]
        status_counts = Counter(str(item.get("raw_payload", {}).get("status") or item.get("raw_payload", {}).get("overall_status") or "unknown") for item in diagnoses)
        return {"diagnosis_count": len(diagnoses), "status_counts": dict(status_counts)}

    def summarize_strategy(self, evidence: list[ExplanationEvidence]) -> dict[str, Any]:
        items = [item for item in evidence if item.source in {"strategy_scoreboard", "strategy_portfolio"}]
        return {"strategy_evidence_count": len(items), "sources": sorted({item.source for item in items})}

    def summarize_budget(self, evidence: list[ExplanationEvidence]) -> dict[str, Any]:
        items = [item for item in evidence if item.source == "strategy_budget"]
        return {"budget_evidence_count": len(items), "advisory_only": bool(items)}

    def summarize_evidence(self, evidence: list[ExplanationEvidence]) -> dict[str, Any]:
        source_counts = Counter(item.source for item in evidence)
        type_counts = Counter(item.evidence_type for item in evidence)
        return {"total": len(evidence), "by_source": dict(source_counts), "by_type": dict(type_counts), "estimated_count": sum(1 for item in evidence if item.estimated), "observed_count": sum(1 for item in evidence if item.observed), "advisory_count": sum(1 for item in evidence if item.advisory)}

    def build_limitations(self, evidence: list[ExplanationEvidence]) -> list[str]:
        limitations: list[str] = []
        if not evidence:
            limitations.append("evidence insufficient")
        if any(item.source == "counterfactual" or item.estimated for item in evidence):
            limitations.append("counterfactual evidence is estimated, not observed")
        if any(item.source == "strategy_budget" for item in evidence):
            limitations.append("strategy budget evidence is advisory only and was not applied")
        for item in evidence:
            flags = {str(flag).lower() for flag in item.risk_flags + item.reason_codes}
            if any("stale" in flag or "missing" in flag for flag in flags):
                limitations.append("some evidence sources are stale or missing")
        return self._dedupe(limitations)

    def build_human_checks(self, evidence: list[ExplanationEvidence], traces: list[DecisionTrace]) -> list[str]:
        checks: list[str] = []
        for item in evidence:
            text = self._text(item.to_dict()).lower()
            if "high_sc" in text or "sc_risk_high" in text or "sc risk" in text:
                checks.append("review_sc_risk")
            if "governance" in text and "block" in text:
                checks.append("review_governance_blocks")
            if item.source == "counterfactual":
                checks.append("review_counterfactual_assumptions")
            if item.source == "strategy_budget":
                checks.append("review_strategy_budget_recommendations")
        if not evidence:
            checks.append("verify_evidence_sources")
        return self._dedupe(checks)

    def _count_text(self, items: list[dict[str, Any]], needle: str) -> int:
        return sum(1 for item in items if needle in self._text(item).lower())

    def _text(self, data: dict[str, Any]) -> str:
        return " ".join(str(data.get(key) or "") for key in ("title", "summary", "confidence", "reason_codes", "risk_flags", "raw_payload"))

    def _min_time(self, evidence: list[ExplanationEvidence]) -> str | None:
        values = sorted(str(item.timestamp) for item in evidence if item.timestamp)
        return values[0] if values else None

    def _max_time(self, evidence: list[ExplanationEvidence]) -> str | None:
        values = sorted(str(item.timestamp) for item in evidence if item.timestamp)
        return values[-1] if values else None

    def _dedupe(self, values: list[str]) -> list[str]:
        result: list[str] = []
        for value in values:
            if value and value not in result:
                result.append(value)
        return result
