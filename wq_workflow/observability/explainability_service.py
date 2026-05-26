from __future__ import annotations

from pathlib import Path
from typing import Any

from wq_workflow import paths

from .decision_trace import DecisionTraceBuilder
from .evidence_loader import ExplanationEvidenceLoader
from .explanation_repository import ExplanationRepository
from .explanation_reporter import ExplanationReporter
from .report_composer import ReportComposer
from .run_explainer import RunExplainer


class ExplainabilityService:
    def __init__(
        self,
        *,
        config: Any | None = None,
        storage: Any | None = None,
        db_path: str | Path | None = None,
        root: str | Path | None = None,
        logger: Any | None = None,
        repository: ExplanationRepository | None = None,
        evidence_loader: ExplanationEvidenceLoader | None = None,
        trace_builder: DecisionTraceBuilder | None = None,
        run_explainer: RunExplainer | None = None,
        report_composer: ReportComposer | None = None,
        reporter: ExplanationReporter | None = None,
    ) -> None:
        self.config = config
        self.storage = storage
        self.root = Path(root or paths.ROOT)
        self.db_path = db_path or getattr(config, "storage_db_path", "runtime/db/workflow.db")
        self.logger = logger
        self.repository = repository or ExplanationRepository(storage=storage, db_path=self.db_path, logger=logger)
        self.evidence_loader = evidence_loader or ExplanationEvidenceLoader(config=config, db_path=self.db_path, root=self.root, logger=logger)
        self.trace_builder = trace_builder or DecisionTraceBuilder()
        self.run_explainer = run_explainer or RunExplainer()
        self.report_composer = report_composer or ReportComposer()
        self.reporter = reporter or ExplanationReporter(
            run_report_path=getattr(config, "run_explain_report_status_path", "runtime/status/run_explain_report.json"),
            daily_report_path=getattr(config, "daily_observability_report_status_path", "runtime/status/daily_observability_report.json"),
            stage_report_path=getattr(config, "stage7_summary_report_status_path", "runtime/status/stage7_summary_report.json"),
            root=self.root,
            logger=logger,
        )
        self.last_result: dict[str, Any] | None = None

    def startup_check(self) -> dict[str, Any]:
        enabled = bool(getattr(self.config, "enable_run_explainability", False))
        auto_run = bool(getattr(self.config, "observability_explainability_auto_run", False))
        try:
            init = self.repository.initialize()
            result = {
                "ok": bool(init.get("ok", False)),
                "enabled": enabled,
                "ready": bool(init.get("ok", False)),
                "mode": "explain_only",
                "auto_run": auto_run,
                "auto_action_allowed": False,
            }
            if enabled and auto_run:
                result["explanations"] = self.generate_explanations()
            return result
        except Exception as exc:
            self._warn("explainability startup failed: %s", exc)
            return {"ok": bool(getattr(self.config, "observability_explainability_fail_open", True)), "enabled": enabled, "fail_open": True, "mode": "explain_only", "error": str(exc), "auto_action_allowed": False}

    def generate_explanations(self) -> dict[str, Any]:
        try:
            evidence = self.evidence_loader.load_all_evidence()
            traces = self.trace_builder.build_traces(evidence)
            explanation = self.run_explainer.explain(evidence, traces)
            daily = self.report_composer.compose_daily_report(explanation)
            stage = self.report_composer.compose_stage_summary(explanation)
            self.repository.save_evidence_batch(evidence)
            for trace in traces:
                self.repository.save_trace(trace)
            self.repository.save_run_explanation(explanation)
            self.repository.save_daily_report(daily)
            self.repository.save_stage_summary(stage)
            writes = self.reporter.write_all(explanation, daily, stage)
            result = {
                "ok": True,
                "mode": "explain_only",
                "evidence_count": len(evidence),
                "trace_count": len(traces),
                "run_explanation_id": explanation.to_dict().get("explanation_id"),
                "daily_report_id": daily.to_dict().get("report_id"),
                "stage_report_id": stage.to_dict().get("report_id"),
                "reports": writes,
                "auto_action_allowed": False,
            }
            self.last_result = result
            return result
        except Exception as exc:
            self._warn("explainability generation failed: %s", exc)
            result = {"ok": bool(getattr(self.config, "observability_explainability_fail_open", True)), "fail_open": True, "mode": "explain_only", "error": str(exc), "auto_action_allowed": False}
            self.last_result = result
            return result

    def get_latest_run_explanation(self) -> Any:
        return self.repository.get_latest_run_explanation()

    def get_latest_daily_report(self) -> Any:
        return self.repository.get_latest_daily_report()

    def get_latest_stage_summary(self) -> Any:
        return self.repository.get_latest_stage_summary()

    def get_status(self) -> dict[str, Any]:
        latest = self.get_latest_run_explanation()
        return {
            "enabled": bool(getattr(self.config, "enable_run_explainability", False)),
            "ready": True,
            "mode": "explain_only",
            "auto_run": bool(getattr(self.config, "observability_explainability_auto_run", False)),
            "status_paths": {
                "run": str(getattr(self.config, "run_explain_report_status_path", "runtime/status/run_explain_report.json")),
                "daily": str(getattr(self.config, "daily_observability_report_status_path", "runtime/status/daily_observability_report.json")),
                "stage": str(getattr(self.config, "stage7_summary_report_status_path", "runtime/status/stage7_summary_report.json")),
            },
            "latest_run_explanation": latest.to_dict() if latest else None,
            "last_result": self.last_result,
            "auto_action_allowed": False,
        }

    def _warn(self, message: str, exc: Exception) -> None:
        try:
            if self.logger is not None:
                self.logger.warning(message, exc)
        except Exception:
            pass
