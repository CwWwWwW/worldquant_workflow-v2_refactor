from __future__ import annotations

from pathlib import Path
from typing import Any

from .budget_allocator import StrategyBudgetAllocator
from .budget_repository import StrategyBudgetRepository
from .budget_reporter import StrategyBudgetReporter
from .budget_schema import StrategyBudgetPlan
from .portfolio_repository import StrategyPortfolioRepository
from .portfolio_service import StrategyPortfolioService


class StrategyBudgetService:
    def __init__(
        self,
        *,
        config: Any | None = None,
        storage: Any | None = None,
        db_path: str | Path | None = None,
        logger: Any | None = None,
        repository: StrategyBudgetRepository | None = None,
        allocator: StrategyBudgetAllocator | None = None,
        reporter: StrategyBudgetReporter | None = None,
        portfolio_repository: StrategyPortfolioRepository | None = None,
        portfolio_service: StrategyPortfolioService | None = None,
        governance_service: Any | None = None,
    ) -> None:
        self.config = config
        self.storage = storage
        self.db_path = db_path or getattr(config, "storage_db_path", "runtime/db/workflow.db")
        self.logger = logger
        self.repository = repository or StrategyBudgetRepository(storage=storage, db_path=self.db_path, logger=logger)
        self.allocator = allocator or StrategyBudgetAllocator(config=config, logger=logger)
        self.reporter = reporter or StrategyBudgetReporter(status_path=getattr(config, "strategy_budget_status_path", "runtime/status/strategy_budget_report.json"), logger=logger)
        self.portfolio_repository = portfolio_repository or StrategyPortfolioRepository(storage=storage, db_path=self.db_path, logger=logger)
        self.portfolio_service = portfolio_service
        self.governance_service = governance_service

    def startup_check(self) -> dict[str, Any]:
        enabled = bool(getattr(self.config, "enable_strategy_budget_allocator", False))
        try:
            init = self.repository.initialize()
            for rule in self.allocator.policy.default_rules():
                self.repository.save_rule(rule)
            result: dict[str, Any] = {
                "ok": bool(init.get("ok", False)),
                "enabled": enabled,
                "mode": getattr(self.config, "strategy_budget_mode", "advisory"),
                "advisory_only": True,
                "auto_apply_allowed": False,
                "auto_apply": False,
            }
            if enabled and bool(getattr(self.config, "strategy_budget_auto_refresh", False)):
                result["refresh"] = self.refresh_budget_plan(total_budget_hint=getattr(self.config, "strategy_budget_total_hint", None))
            return result
        except Exception as exc:
            self._warn("strategy budget startup failed: %s", exc)
            return {"ok": bool(getattr(self.config, "strategy_budget_fail_open", True)), "enabled": enabled, "fail_open": True, "error": str(exc)}

    def refresh_budget_plan(self, total_budget_hint: int | None = None) -> dict[str, Any]:
        try:
            hint = total_budget_hint if total_budget_hint is not None else getattr(self.config, "strategy_budget_total_hint", None)
            states = self._load_states()
            plan = self.allocator.build_budget_plan(states, total_budget_hint=hint)
            for allocation in plan.allocations:
                self.repository.save_allocation(allocation)
            self.repository.save_plan(plan)
            report = self.reporter.build_report(plan, mode=getattr(self.config, "strategy_budget_mode", "advisory"))
            self.repository.save_report(report)
            status = self.reporter.update(plan, enabled=bool(getattr(self.config, "enable_strategy_budget_allocator", False)), mode=getattr(self.config, "strategy_budget_mode", "advisory"))
            return {"ok": True, "enabled": bool(getattr(self.config, "enable_strategy_budget_allocator", False)), "plan_id": plan.plan_id, "report_id": report.report_id, "status": status, "advisory_only": True, "auto_apply_allowed": False}
        except Exception as exc:
            self._warn("strategy budget refresh failed: %s", exc)
            return {"ok": bool(getattr(self.config, "strategy_budget_fail_open", True)), "enabled": bool(getattr(self.config, "enable_strategy_budget_allocator", False)), "fail_open": True, "error": str(exc)}

    def get_latest_budget_plan(self) -> StrategyBudgetPlan | None:
        return self.repository.get_latest_plan()

    def get_strategy_allocation(self, strategy_id: str) -> Any:
        latest = self.get_latest_budget_plan()
        if latest is not None:
            for allocation in latest.allocations:
                if allocation.strategy_id == strategy_id:
                    return allocation
        rows = self.repository.list_allocations(strategy_id=strategy_id, limit=1)
        return rows[0] if rows else None

    def list_budget_allocations(self) -> list[Any]:
        latest = self.get_latest_budget_plan()
        if latest is not None:
            return latest.allocations
        return self.repository.list_allocations()

    def get_budget_report(self) -> Any:
        return self.repository.get_latest_report()

    def get_status(self) -> dict[str, Any]:
        latest = self.get_latest_budget_plan()
        return {
            "enabled": bool(getattr(self.config, "enable_strategy_budget_allocator", False)),
            "mode": getattr(self.config, "strategy_budget_mode", "advisory"),
            "advisory_only": True,
            "auto_apply_allowed": False,
            "auto_apply": False,
            "latest_plan_id": latest.plan_id if latest else "",
            "status_path": str(getattr(self.config, "strategy_budget_status_path", "runtime/status/strategy_budget_report.json")),
        }

    def _load_states(self) -> list[Any]:
        try:
            if self.portfolio_service is not None:
                latest = self.portfolio_service.get_latest_portfolio()
                if latest is None:
                    refresh = self.portfolio_service.refresh_portfolio()
                    if not refresh.get("ok"):
                        self._warn("strategy portfolio refresh before budget failed: %s", Exception(str(refresh.get("error", "unknown"))))
                    latest = self.portfolio_service.get_latest_portfolio()
                if latest is not None:
                    return list(latest.states or [])
        except Exception as exc:
            self._warn("strategy budget portfolio service read failed: %s", exc)
        try:
            latest = self.portfolio_repository.get_latest_portfolio()
            if latest is not None:
                return list(latest.states or [])
            states = self.portfolio_repository.list_states()
            return list(states or [])
        except Exception as exc:
            self._warn("strategy budget portfolio repository read failed: %s", exc)
            return []

    def _warn(self, message: str, exc: Exception) -> None:
        try:
            if self.logger is not None:
                self.logger.warning(message, exc)
        except Exception:
            pass
