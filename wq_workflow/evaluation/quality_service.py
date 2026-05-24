from __future__ import annotations

from typing import Any

from wq_workflow.core_types import PlatformSCResult, QualityResult, SimulationResult


class QualityService:
    def __init__(self, config: Any | None = None) -> None:
        self.config = config

    def evaluate(self, simulation_result: SimulationResult | dict[str, Any] | None, platform_sc: PlatformSCResult | dict[str, Any] | None = None) -> QualityResult:
        raw = simulation_result.to_dict() if hasattr(simulation_result, "to_dict") else (simulation_result or {})
        text = str(raw.get("testing_status") or raw.get("text") or raw.get("raw_text") or "")
        try:
            from wq_workflow.quality import parse_quality_report

            report = parse_quality_report(text) if text else None
        except Exception as exc:
            return QualityResult(passed=False, reason=str(exc), warnings=["quality_parse_failed"], raw_payload={"simulation_result": raw})
        if report is None:
            ok = bool(raw.get("ok") or raw.get("passed"))
            return QualityResult(passed=ok, reason="legacy_status", raw_payload={"simulation_result": raw})
        return QualityResult(
            passed=bool(getattr(report, "passed", False)),
            reason=str(getattr(report, "status", "")),
            testing_status=text,
            fail_count=int(getattr(report, "fail_count", 0) or 0),
            pending_count=int(getattr(report, "pending_count", 0) or 0),
            pass_count=int(getattr(report, "pass_count", 0) or 0),
            raw_payload={"quality_report": getattr(report, "__dict__", {}), "simulation_result": raw},
        )
