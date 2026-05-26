from __future__ import annotations

from pathlib import Path
from typing import Any

from wq_workflow import paths

from .explanation_schema import DailyRunReport, RunExplanation, StageSummaryReport
from .utils import atomic_write_json, utc_now_iso


class ExplanationReporter:
    def __init__(
        self,
        *,
        run_report_path: str | Path = "runtime/status/run_explain_report.json",
        daily_report_path: str | Path = "runtime/status/daily_observability_report.json",
        stage_report_path: str | Path = "runtime/status/stage7_summary_report.json",
        root: str | Path | None = None,
        logger: Any | None = None,
    ) -> None:
        self.root = Path(root or paths.ROOT)
        self.run_report_path = self._resolve(run_report_path)
        self.daily_report_path = self._resolve(daily_report_path)
        self.stage_report_path = self._resolve(stage_report_path)
        self.logger = logger

    def write_run_report(self, explanation: RunExplanation) -> dict[str, Any]:
        payload = self.build_run_payload(explanation)
        return self._write(self.run_report_path, payload)

    def write_daily_report(self, report: DailyRunReport) -> dict[str, Any]:
        payload = self.build_daily_payload(report)
        return self._write(self.daily_report_path, payload)

    def write_stage_report(self, report: StageSummaryReport) -> dict[str, Any]:
        payload = self.build_stage_payload(report)
        return self._write(self.stage_report_path, payload)

    def write_all(self, explanation: RunExplanation, daily: DailyRunReport, stage: StageSummaryReport) -> dict[str, Any]:
        return {"run": self.write_run_report(explanation), "daily": self.write_daily_report(daily), "stage": self.write_stage_report(stage)}

    def build_run_payload(self, explanation: RunExplanation) -> dict[str, Any]:
        data = RunExplanation.from_dict(explanation).to_dict()
        return {
            "updated_at": utc_now_iso(),
            "enabled": True,
            "mode": "explain_only",
            "run_summary": data.get("run_summary", ""),
            "key_findings": data.get("key_findings", []),
            "decision_traces": data.get("decision_traces", []),
            "alerts_summary": data.get("alerts_summary", {}),
            "diagnosis_summary": data.get("diagnosis_summary", {}),
            "strategy_summary": data.get("strategy_summary", {}),
            "budget_summary": data.get("budget_summary", {}),
            "evidence_summary": data.get("evidence_summary", {}),
            "limitations": data.get("limitations", []),
            "recommended_human_checks": data.get("recommended_human_checks", []),
            "auto_action_allowed": False,
        }

    def build_daily_payload(self, report: DailyRunReport) -> dict[str, Any]:
        data = DailyRunReport.from_dict(report).to_dict()
        return {
            "updated_at": utc_now_iso(),
            "enabled": True,
            "mode": "explain_only",
            "date": data.get("date"),
            "overall_summary": data.get("overall_summary", ""),
            "health_status": data.get("health_status", "unknown"),
            "key_metrics": data.get("key_metrics", {}),
            "key_alerts": data.get("key_alerts", []),
            "key_diagnoses": data.get("key_diagnoses", []),
            "strategy_explanations": data.get("strategy_explanations", []),
            "budget_explanations": data.get("budget_explanations", []),
            "offline_evidence_summary": data.get("offline_evidence_summary", {}),
            "counterfactual_limitations": data.get("counterfactual_limitations", []),
            "recommended_human_checks": data.get("recommended_human_checks", []),
            "auto_action_allowed": False,
        }

    def build_stage_payload(self, report: StageSummaryReport) -> dict[str, Any]:
        data = StageSummaryReport.from_dict(report).to_dict()
        return {
            "updated_at": utc_now_iso(),
            "enabled": True,
            "mode": "explain_only",
            "stage_name": data.get("stage_name", "phase7-observability"),
            "completed_substages": data.get("completed_substages", []),
            "generated_reports": data.get("generated_reports", []),
            "key_capabilities": data.get("key_capabilities", []),
            "known_limitations": data.get("known_limitations", []),
            "next_stage_recommendations": data.get("next_stage_recommendations", []),
            "auto_action_allowed": False,
        }

    def _write(self, path: Path, payload: dict[str, Any]) -> dict[str, Any]:
        result = atomic_write_json(path, payload, backup_corrupt=True)
        if not result.get("ok"):
            self._warn("explanation report write failed: %s", result.get("error"))
        return result

    def _resolve(self, value: str | Path) -> Path:
        path = Path(value)
        return path if path.is_absolute() else self.root / path

    def _warn(self, message: str, value: Any) -> None:
        try:
            if self.logger is not None:
                self.logger.warning(message, value)
        except Exception:
            pass
