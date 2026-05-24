from __future__ import annotations

from typing import Any

from wq_workflow.core_types import CandidateDraft, PlatformSCResult, ServiceResult, SimulationResult


class PlatformService:
    """Thin platform facade; all Playwright page details stay in platform/legacy facades."""

    def __init__(self, page: Any | None = None, config: Any | None = None, logger: Any | None = None) -> None:
        self.page = page
        self.config = config
        self.logger = logger

    async def submit_backtest(self, candidate: CandidateDraft) -> ServiceResult[SimulationResult]:
        if self.page is None or self.config is None:
            return ServiceResult(ok=False, error="page/config unavailable", source="platform.submitter")
        try:
            from wq_workflow.simulate import run_platform_backtest_attempt

            raw = await run_platform_backtest_attempt(self.page, candidate.expression, candidate.alpha_id, self.config)
            data = _simulation_from_legacy(raw, alpha_id=candidate.alpha_id)
            return ServiceResult(ok=data.ok, data=data, source="platform.submitter", raw_payload={"legacy_result": _legacy_to_dict(raw)})
        except Exception as exc:
            return ServiceResult(ok=False, error=str(exc), source="platform.submitter")

    async def wait_result(self, alpha_id: str) -> ServiceResult[SimulationResult]:
        return ServiceResult(ok=False, error="wait_result requires legacy FSM context; use simulate facade", source="platform.result_watcher")

    async def parse_result(self) -> ServiceResult[SimulationResult]:
        return ServiceResult(ok=False, error="parse_result requires legacy FSM context; use simulate facade", source="platform.result_parser")

    async def collect_sc(self, alpha_id: str = "") -> ServiceResult[PlatformSCResult]:
        if self.page is None:
            return ServiceResult(ok=False, error="page unavailable", source="platform.sc_collector")
        try:
            from wq_workflow.platform.sc_collector import PlatformSCCollector

            collector = PlatformSCCollector(self.logger, timeout=int(getattr(self.config, "platform_sc_timeout_seconds", 90) or 90))
            result = await collector.collect(self.page)
            return ServiceResult(ok=result.status == "complete", data=result, source="platform.sc_collector", raw_payload=result.to_payload())
        except Exception as exc:
            return ServiceResult(ok=False, error=str(exc), source="platform.sc_collector")


def _legacy_to_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if hasattr(value, "to_dict"):
        try:
            return value.to_dict()
        except Exception:
            pass
    return dict(getattr(value, "__dict__", {}) or {})


def _simulation_from_legacy(value: Any, alpha_id: str = "") -> SimulationResult:
    raw = _legacy_to_dict(value)
    metrics = raw.get("metrics") if isinstance(raw.get("metrics"), dict) else {}
    ok = bool(raw.get("ok", raw.get("success", raw.get("passed", False))))
    return SimulationResult(
        alpha_id=str(raw.get("alpha_id") or raw.get("alpha_name") or alpha_id or ""),
        simulation_id=str(raw.get("simulation_id") or raw.get("id") or ""),
        ok=ok,
        metrics=metrics,
        testing_status=str(raw.get("testing_status") or raw.get("status") or ""),
        result_fingerprint=str(raw.get("result_fingerprint") or raw.get("fingerprint") or ""),
        freshness_score=raw.get("freshness_score"),
        raw_payload=raw,
        error=str(raw.get("error") or ""),
    )
