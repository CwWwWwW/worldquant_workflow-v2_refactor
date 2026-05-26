from __future__ import annotations

from typing import Any

from .explanation_schema import DailyRunReport, RunExplanation, StageSummaryReport
from .utils import utc_now_iso


class ReportComposer:
    def compose_daily_report(self, run_explanation: RunExplanation, date: str | None = None) -> DailyRunReport:
        run = RunExplanation.from_dict(run_explanation)
        generated_at = utc_now_iso()
        return DailyRunReport(
            report_id=f"daily_observability_report:{date or generated_at[:10]}",
            generated_at=generated_at,
            date=date or generated_at[:10],
            overall_summary=run.run_summary,
            health_status=self._health_status(run),
            key_metrics=self.extract_key_metrics(run),
            key_alerts=self.extract_key_alerts(run),
            key_diagnoses=self.extract_key_diagnoses(run),
            strategy_explanations=self.build_strategy_explanations(run),
            budget_explanations=self.build_budget_explanations(run),
            offline_evidence_summary=self.build_offline_evidence_summary(run),
            counterfactual_limitations=self.build_counterfactual_limitations(run),
            recommended_human_checks=list(run.recommended_human_checks or []),
            auto_action_allowed=False,
            raw_payload={"mode": "explain_only", "run_explanation_id": run.explanation_id},
        )

    def compose_stage_summary(self, run_explanation: RunExplanation) -> StageSummaryReport:
        run = RunExplanation.from_dict(run_explanation)
        generated_at = utc_now_iso()
        return StageSummaryReport(
            report_id=f"stage7_summary_report:{generated_at}",
            generated_at=generated_at,
            stage_name="phase7-observability",
            summary="Phase 7 observability now includes metrics, advisory health diagnosis, and explain-only run reports.",
            completed_substages=["7A", "7B", "7C"],
            generated_reports=[
                "observability_metrics.json",
                "observability_alerts.json",
                "health_diagnosis.json",
                "run_explain_report.json",
                "daily_observability_report.json",
                "stage7_summary_report.json",
            ],
            key_capabilities=[
                "observability metrics collection",
                "advisory drift alert health diagnosis",
                "explain-only evidence loading",
                "decision trace summaries",
                "daily and stage run reports",
            ],
            known_limitations=list(run.limitations or []),
            next_stage_recommendations=["review reports manually before any operational change"],
            auto_action_allowed=False,
            raw_payload={"mode": "explain_only", "run_explanation_id": run.explanation_id},
        )

    def extract_key_metrics(self, run_explanation: RunExplanation) -> dict[str, Any]:
        run = RunExplanation.from_dict(run_explanation)
        return {"evidence_summary": run.evidence_summary, "alerts_summary": run.alerts_summary, "diagnosis_summary": run.diagnosis_summary}

    def extract_key_alerts(self, run_explanation: RunExplanation) -> list[str]:
        run = RunExplanation.from_dict(run_explanation)
        values: list[str] = []
        for trace in run.decision_traces:
            for item in trace.evidence:
                if item.evidence_type == "alert":
                    values.append(f"{item.title}: {item.summary}")
        return values[:20]

    def extract_key_diagnoses(self, run_explanation: RunExplanation) -> list[str]:
        run = RunExplanation.from_dict(run_explanation)
        values: list[str] = []
        for trace in run.decision_traces:
            for item in trace.evidence:
                if item.evidence_type == "diagnosis":
                    values.append(f"{item.title}: {item.summary}")
        return values[:20]

    def build_strategy_explanations(self, run_explanation: RunExplanation) -> list[str]:
        run = RunExplanation.from_dict(run_explanation)
        values = [trace.explanation for trace in run.decision_traces if trace.decision_type == "strategy_selection"]
        return [value for value in values if value][:10]

    def build_budget_explanations(self, run_explanation: RunExplanation) -> list[str]:
        run = RunExplanation.from_dict(run_explanation)
        values = [trace.explanation for trace in run.decision_traces if trace.decision_type == "budget_recommendation"]
        if run.budget_summary.get("advisory_only"):
            values.append("Strategy budget recommendations are advisory only and were not applied by explainability.")
        return [value for value in values if value][:10]

    def build_offline_evidence_summary(self, run_explanation: RunExplanation) -> dict[str, Any]:
        run = RunExplanation.from_dict(run_explanation)
        counts: dict[str, int] = {"decision_snapshot": 0, "offline_replay": 0, "actual_outcome": 0}
        for trace in run.decision_traces:
            for item in trace.evidence:
                if item.source in counts:
                    counts[item.source] += 1
                if item.evidence_type == "actual_outcome":
                    counts["actual_outcome"] += 1
        return counts

    def build_counterfactual_limitations(self, run_explanation: RunExplanation) -> list[str]:
        run = RunExplanation.from_dict(run_explanation)
        return [item for item in run.limitations if "counterfactual" in item.lower()]

    def _health_status(self, run: RunExplanation) -> str:
        counts = run.diagnosis_summary.get("status_counts", {}) if isinstance(run.diagnosis_summary, dict) else {}
        for status in ("critical", "degraded", "watch", "healthy"):
            if counts.get(status):
                return status
        if run.alerts_summary.get("critical_count"):
            return "critical"
        if run.alerts_summary.get("warning_count"):
            return "watch"
        return "unknown"
