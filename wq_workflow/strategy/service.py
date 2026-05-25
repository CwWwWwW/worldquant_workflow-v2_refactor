from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from .evidence_loader import StrategyEvidenceLoader
from .registry import StrategyRegistry
from .repository import StrategyRepository
from .reporter import StrategyReporter
from .scoreboard import StrategyScoreboardBuilder
from .schema import StrategyScoreboard, utc_now_iso
from .scorer import StrategyScorer


class StrategyService:
    def __init__(self, *, config: Any | None = None, storage: Any | None = None, db_path: str | Path | None = None, logger: Any | None = None, repository: StrategyRepository | None = None, registry: StrategyRegistry | None = None, evidence_loader: StrategyEvidenceLoader | None = None, scorer: StrategyScorer | None = None, reporter: StrategyReporter | None = None) -> None:
        self.config = config
        self.storage = storage
        self.db_path = db_path if db_path is not None else getattr(config, "storage_db_path", "runtime/db/workflow.db")
        self.logger = logger
        self.repository = repository or StrategyRepository(storage=storage, db_path=self.db_path, logger=logger)
        self.registry = registry or StrategyRegistry(repositories=None, config=config, logger=logger, profile_repository=self.repository)
        self.evidence_loader = evidence_loader or StrategyEvidenceLoader(storage=storage, db_path=self.db_path, config=config, logger=logger)
        self.scorer = scorer or StrategyScorer(config=config, logger=logger)
        self.reporter = reporter or StrategyReporter(status_path=getattr(config, "strategy_scoreboard_status_path", "runtime/status/strategy_scoreboard.json"), logger=logger)
        self.last_error = ""

    def startup_check(self) -> dict[str, Any]:
        if not bool(getattr(self.config, "enable_strategy_registry", True)):
            return {"ok": True, "enabled": False, "mode": getattr(self.config, "strategy_registry_mode", "advisory")}
        try:
            init = self.repository.initialize()
            self.registry.ensure_default_strategies()
            result: dict[str, Any] = {"ok": bool(init.get("ok", False)), "enabled": True, "mode": getattr(self.config, "strategy_registry_mode", "advisory"), "profile_count": len(self.registry.list_profiles())}
            if bool(getattr(self.config, "strategy_scoreboard_auto_refresh", False)):
                result["refresh"] = self.refresh_scoreboard()
            return result
        except Exception as exc:
            self.last_error = str(exc)
            self._warn("strategy startup failed: %s", exc)
            return {"ok": bool(getattr(self.config, "strategy_fail_open", True)), "enabled": True, "fail_open": True, "error": str(exc)}

    def refresh_scoreboard(self) -> dict[str, Any]:
        if not bool(getattr(self.config, "enable_strategy_registry", True)):
            return {"ok": True, "enabled": False, "refreshed": False}
        try:
            builder = StrategyScoreboardBuilder(self.registry, self.evidence_loader, self.scorer, config=self.config, logger=self.logger)
            evidence = self.evidence_loader.load_all_evidence()
            profiles = self.registry.list_profiles()
            scores = builder.rank_scores([self.scorer.score_strategy(profile, evidence) for profile in profiles])
            signals = []
            for profile in profiles:
                signals.extend(self.scorer.build_signals(profile, evidence))
            scoreboard = StrategyScoreboard(
                scoreboard_id=f"strategy_scoreboard:{uuid.uuid4().hex}",
                generated_at=utc_now_iso(),
                profiles=profiles,
                scores=scores,
                signals=signals,
                evidence_summary=builder.summarize_evidence(evidence),
                warnings=list(dict.fromkeys(builder.generate_warnings(scores, evidence) + getattr(self.evidence_loader, "warnings", [])))[-100:],
                raw_payload={"mode": getattr(self.config, "strategy_registry_mode", "advisory"), "advisory_only": True},
            )
            for profile in scoreboard.profiles:
                self.repository.save_profile(profile)
            for item in evidence:
                self.repository.save_evidence(item)
            for signal in scoreboard.signals:
                self.repository.save_signal(signal)
            for score in scoreboard.scores:
                self.repository.save_score(score)
            self.repository.save_scoreboard(scoreboard)
            report = self.reporter.update(scoreboard, enabled=True, mode=getattr(self.config, "strategy_registry_mode", "advisory"))
            return {"ok": True, "enabled": True, "scoreboard_id": scoreboard.scoreboard_id, "report": report}
        except Exception as exc:
            self.last_error = str(exc)
            self._warn("strategy refresh failed: %s", exc)
            return {"ok": bool(getattr(self.config, "strategy_fail_open", True)), "enabled": True, "fail_open": True, "error": str(exc)}

    def get_latest_scoreboard(self) -> StrategyScoreboard | None:
        return self.repository.get_latest_scoreboard()

    def get_strategy_score(self, strategy_id: str) -> Any:
        return self.repository.get_score(strategy_id)

    def list_strategy_scores(self) -> list[Any]:
        return self.repository.list_scores()

    def get_strategy_evidence_summary(self) -> dict[str, Any]:
        latest = self.get_latest_scoreboard()
        if latest is not None:
            return latest.evidence_summary
        builder = StrategyScoreboardBuilder(self.registry, self.evidence_loader, self.scorer, config=self.config, logger=self.logger)
        return builder.summarize_evidence(self.evidence_loader.load_all_evidence())

    def get_status(self) -> dict[str, Any]:
        latest = self.get_latest_scoreboard()
        return {
            "enabled": bool(getattr(self.config, "enable_strategy_registry", True)),
            "mode": getattr(self.config, "strategy_registry_mode", "advisory"),
            "ready": self.last_error == "",
            "latest_scoreboard_id": latest.scoreboard_id if latest else "",
            "status_path": str(getattr(self.config, "strategy_scoreboard_status_path", "runtime/status/strategy_scoreboard.json")),
            "last_error": self.last_error,
        }

    def _warn(self, message: str, exc: Exception) -> None:
        try:
            if self.logger is not None:
                self.logger.warning(message, exc)
        except Exception:
            pass
