from __future__ import annotations

from pathlib import Path
from typing import Any

from .portfolio_policy import ChampionChallengerPolicy
from .portfolio_repository import StrategyPortfolioRepository
from .portfolio_reporter import StrategyPortfolioReporter
from .portfolio_schema import StrategyPortfolio
from .repository import StrategyRepository
from .service import StrategyService


class StrategyPortfolioService:
    def __init__(self, *, config: Any | None = None, storage: Any | None = None, db_path: str | Path | None = None, logger: Any | None = None, repository: StrategyPortfolioRepository | None = None, strategy_repository: StrategyRepository | None = None, strategy_service: StrategyService | None = None, policy: ChampionChallengerPolicy | None = None, reporter: StrategyPortfolioReporter | None = None, governance_service: Any | None = None) -> None:
        self.config = config
        self.storage = storage
        self.db_path = db_path if db_path is not None else getattr(config, "storage_db_path", "runtime/db/workflow.db")
        self.logger = logger
        self.repository = repository or StrategyPortfolioRepository(storage=storage, db_path=self.db_path, logger=logger)
        self.strategy_repository = strategy_repository or StrategyRepository(storage=storage, db_path=self.db_path, logger=logger)
        self.strategy_service = strategy_service
        self.policy = policy or ChampionChallengerPolicy(config=config, logger=logger)
        self.reporter = reporter or StrategyPortfolioReporter(status_path=getattr(config, "strategy_portfolio_status_path", "runtime/status/strategy_portfolio_report.json"), logger=logger)
        self.governance_service = governance_service
        self.last_error = ""

    def startup_check(self) -> dict[str, Any]:
        enabled = bool(getattr(self.config, "enable_strategy_champion_challenger", False))
        try:
            init = self.repository.initialize()
            result: dict[str, Any] = {"ok": bool(init.get("ok", False)), "enabled": enabled, "mode": getattr(self.config, "strategy_portfolio_mode", "advisory"), "advisory_only": True}
            if enabled and bool(getattr(self.config, "strategy_portfolio_auto_refresh", False)):
                result["refresh"] = self.refresh_portfolio()
            return result
        except Exception as exc:
            self.last_error = str(exc)
            self._warn("strategy portfolio startup failed: %s", exc)
            return {"ok": bool(getattr(self.config, "strategy_portfolio_fail_open", True)), "enabled": enabled, "fail_open": True, "error": str(exc)}

    def refresh_portfolio(self) -> dict[str, Any]:
        try:
            scores = self._load_scores()
            current_states = {state.strategy_id: state.to_dict() for state in self.repository.list_states()}
            portfolio = self.policy.evaluate_scores(scores, current_states=current_states)
            for state in portfolio.states:
                self.repository.save_state(state)
            for transition in portfolio.transitions:
                transition.auto_apply_allowed = False
                self.repository.save_transition(transition)
            self.repository.save_portfolio(portfolio)
            report = self.reporter.build_report(portfolio, mode=getattr(self.config, "strategy_portfolio_mode", "advisory"))
            self.repository.save_report(report)
            status = self.reporter.update(portfolio, enabled=True, mode=getattr(self.config, "strategy_portfolio_mode", "advisory"))
            return {"ok": True, "enabled": True, "portfolio_id": portfolio.portfolio_id, "report_id": report.report_id, "status": status}
        except Exception as exc:
            self.last_error = str(exc)
            self._warn("strategy portfolio refresh failed: %s", exc)
            return {"ok": bool(getattr(self.config, "strategy_portfolio_fail_open", True)), "enabled": True, "fail_open": True, "error": str(exc)}

    def select_strategy(self, task_name: str | None = None) -> dict[str, Any]:
        """Compatibility selection hook for the advisory portfolio service.

        The Phase 6B portfolio service is advisory/report-only. It must not
        silently replace the legacy production selector, so the compatible
        workflow hook returns the legacy champion unless a later explicit
        production promotion path is added.
        """

        return {
            "strategy_id": "legacy_champion",
            "strategy_type": "legacy",
            "role": "champion",
            "status": "active",
            "task_name": task_name or "",
            "advisory_only": True,
        }

    def record_strategy_decision(
        self,
        strategy: dict[str, Any],
        workflow_context: dict[str, Any],
        selected: bool,
        shadow: bool,
        score: float | None = None,
    ) -> None:
        """Fail-open compatibility hook used by the workflow skeleton."""

        try:
            repository = getattr(self, "strategy_repository", None)
            if repository is None or not hasattr(repository, "insert_strategy_decision"):
                return
            context = workflow_context if isinstance(workflow_context, dict) else {}
            strategy_payload = strategy if isinstance(strategy, dict) else {}
            repository.insert_strategy_decision(
                {
                    "strategy_id": strategy_payload.get("strategy_id", "legacy_champion"),
                    "alpha_id": context.get("alpha_id", ""),
                    "decision_type": context.get("decision_type", "strategy_selection"),
                    "selected": bool(selected),
                    "shadow": bool(shadow),
                    "score": score,
                    "model_version": strategy_payload.get("model_version", ""),
                    "raw_payload": {"strategy": strategy_payload, "workflow_context": context},
                }
            )
        except Exception:
            return

    def get_latest_portfolio(self) -> StrategyPortfolio | None:
        return self.repository.get_latest_portfolio()

    def get_strategy_state(self, strategy_id: str) -> Any:
        return self.repository.get_state(strategy_id)

    def list_strategy_states(self) -> list[Any]:
        return self.repository.list_states()

    def get_portfolio_report(self) -> Any:
        return self.repository.get_latest_report()

    def get_status(self) -> dict[str, Any]:
        latest = self.get_latest_portfolio()
        return {
            "enabled": bool(getattr(self.config, "enable_strategy_champion_challenger", False)),
            "mode": getattr(self.config, "strategy_portfolio_mode", "advisory"),
            "ready": self.last_error == "",
            "latest_portfolio_id": latest.portfolio_id if latest else "",
            "status_path": str(getattr(self.config, "strategy_portfolio_status_path", "runtime/status/strategy_portfolio_report.json")),
            "advisory_only": True,
            "auto_apply_allowed": False,
            "last_error": self.last_error,
        }

    def _load_scores(self) -> list[Any]:
        if self.strategy_service is not None:
            latest = self.strategy_service.get_latest_scoreboard()
            if latest is None:
                refresh = self.strategy_service.refresh_scoreboard()
                if not refresh.get("ok"):
                    self._warn("strategy scoreboard refresh failed before portfolio: %s", Exception(str(refresh.get("error", "unknown"))))
                latest = self.strategy_service.get_latest_scoreboard()
            if latest is not None:
                return latest.scores
        latest = self.strategy_repository.get_latest_scoreboard()
        if latest is not None:
            return latest.scores
        return self.strategy_repository.list_scores()

    def _warn(self, message: str, exc: Exception) -> None:
        try:
            if self.logger is not None:
                self.logger.warning(message, exc)
        except Exception:
            pass
