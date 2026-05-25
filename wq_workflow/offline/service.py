from __future__ import annotations

from pathlib import Path
from typing import Any

from .decision_snapshot import DecisionSnapshotBuilder
from .counterfactual_dataset import CounterfactualDatasetLoader
from .counterfactual_evaluator import CounterfactualEvaluator
from .counterfactual_reporter import CounterfactualReporter
from .counterfactual_repository import CounterfactualRepository
from .replay_dataset import ReplayDatasetLoader
from .replay_engine import ReplayEngine
from .replay_reporter import ReplayReporter
from .replay_repository import ReplayRepository
from .repository import DecisionSnapshotRepository
from .reporter import DecisionSnapshotReporter
from .schema import CounterfactualEstimate, CounterfactualRequest, DecisionOutcome, DecisionSnapshot, ReplayDatasetFilter, ReplayRun, utc_now_iso


class DecisionSnapshotService:
    def __init__(
        self,
        *,
        config: Any | None = None,
        repository: DecisionSnapshotRepository | None = None,
        reporter: DecisionSnapshotReporter | None = None,
        storage: Any | None = None,
        db_path: str | Path | None = None,
        logger: Any | None = None,
        builder: DecisionSnapshotBuilder | None = None,
    ) -> None:
        self.config = config
        self.logger = logger
        self.enabled = bool(getattr(config, "enable_decision_snapshots", True))
        self.fail_open = bool(getattr(config, "decision_snapshot_fail_open", True))
        self.repository = repository or DecisionSnapshotRepository(storage=storage, db_path=db_path or getattr(config, "storage_db_path", None), logger=logger)
        status_path = getattr(config, "decision_snapshot_status_path", "runtime/status/decision_snapshot_status.json")
        self.reporter = reporter or DecisionSnapshotReporter(repository=self.repository, status_path=status_path, logger=logger)
        self.builder = builder or DecisionSnapshotBuilder()
        self.available = True
        self.warnings: list[str] = []

    def startup_check(self) -> dict[str, Any]:
        if not self.enabled:
            return {"ok": True, "enabled": False, "available": False, "tracking_only": True}
        try:
            result = self.repository.initialize()
            if not result.get("ok", False):
                self.available = False
                self._warn(str(result.get("error") or getattr(self.repository, "last_error", "repository_initialize_failed")))
                return {"ok": False, "enabled": True, "available": False, "warnings": list(self.warnings)}
            report = self.update_report()
            return {"ok": True, "enabled": True, "available": True, "tracking_only": True, "status_path": getattr(self.reporter, "status_path", ""), "report": report, "warnings": list(self.warnings)}
        except Exception as exc:
            self.available = False
            self._warn(f"startup_check_failed: {exc}")
            return {"ok": False, "enabled": True, "available": False, "warnings": list(self.warnings)}

    def record_decision(self, decision_type: str, context: Any) -> DecisionSnapshot | None:
        if not self.enabled or not self.available:
            return None
        if not self._type_enabled(decision_type):
            return None
        try:
            snapshot = self.builder.build_snapshot(decision_type, context if isinstance(context, dict) else {})
            result = self.repository.save_snapshot(snapshot)
            if not result.get("ok", False):
                self._warn(str(result.get("error") or getattr(self.repository, "last_error", "save_snapshot_failed")))
                return None
            try:
                self.repository.update_summary(snapshot.decision_type)
            except Exception:
                pass
            return snapshot
        except Exception as exc:
            self._warn(f"record_decision_failed: {exc}")
            return None

    def record_outcome(self, alpha_id: str | None, outcome_context: Any) -> list[DecisionOutcome]:
        if not self.enabled or not self.available:
            return []
        data = outcome_context if isinstance(outcome_context, dict) else {}
        try:
            snapshots = self.repository.find_snapshots_by_alpha(str(alpha_id or "")) if alpha_id else []
            explicit_decision_id = data.get("decision_id")
            if explicit_decision_id and not any(item.decision_id == explicit_decision_id for item in snapshots):
                snapshot = self.repository.get_snapshot(str(explicit_decision_id))
                if snapshot is not None:
                    snapshots.append(snapshot)
            outcomes: list[DecisionOutcome] = []
            for snapshot in snapshots:
                outcome = DecisionOutcome(
                    outcome_id=str(data.get("outcome_id") or _outcome_id(snapshot.decision_id, snapshot.alpha_id or alpha_id, data)),
                    decision_id=snapshot.decision_id,
                    alpha_id=snapshot.alpha_id or alpha_id,
                    success=_pick_bool(data, "success"),
                    reward=_pick_float(data, "reward"),
                    sharpe=_pick_float(data, "sharpe"),
                    fitness=_pick_float(data, "fitness"),
                    returns=_pick_float(data, "returns"),
                    turnover=_pick_float(data, "turnover"),
                    drawdown=_pick_float(data, "drawdown"),
                    margin=_pick_float(data, "margin"),
                    platform_sc_status=_pick_text(data, "platform_sc_status"),
                    platform_sc_abs_max=_pick_float(data, "platform_sc_abs_max"),
                    quality_passed=_pick_bool(data, "quality_passed"),
                    failure_type=_pick_text(data, "failure_type") or _pick_text(data, "failure_reason"),
                    raw_payload=_clean_dict(data.get("raw_payload") or data),
                )
                saved = self.repository.save_outcome(outcome)
                if saved.get("ok", False):
                    self.repository.update_snapshot_outcome(snapshot.decision_id, outcome.to_dict())
                    self.repository.update_summary(snapshot.decision_type)
                    outcomes.append(outcome)
            return outcomes
        except Exception as exc:
            self._warn(f"record_outcome_failed: {exc}")
            return []

    def update_report(self) -> dict[str, Any]:
        if not self.enabled:
            return {"ok": True, "enabled": False, "skipped": True}
        try:
            for snapshot in self.repository.list_snapshots(limit=5000):
                if snapshot.decision_type:
                    self.repository.update_summary(snapshot.decision_type)
            return self.reporter.update(enabled=self.enabled, warnings=list(self.warnings))
        except Exception as exc:
            self._warn(f"update_report_failed: {exc}")
            return {"ok": False, "enabled": self.enabled, "warnings": list(self.warnings)}

    def get_status(self) -> dict[str, Any]:
        try:
            return {
                "ok": True,
                "enabled": self.enabled,
                "available": self.available,
                "snapshot_count": self.repository.count_snapshots(),
                "outcome_count": self.repository.count_outcomes(),
                "summaries": [item.to_dict() for item in self.repository.list_summaries()],
                "warnings": list(self.warnings),
            }
        except Exception as exc:
            self._warn(f"get_status_failed: {exc}")
            return {"ok": False, "enabled": self.enabled, "available": False, "warnings": list(self.warnings)}

    def _type_enabled(self, decision_type: str) -> bool:
        key = f"decision_snapshot_record_{str(decision_type or 'unknown')}"
        return bool(getattr(self.config, key, True)) if self.config is not None else True

    def _warn(self, message: str) -> None:
        self.warnings.append(message)
        self.warnings = self.warnings[-50:]
        try:
            if self.logger is not None:
                self.logger.warning("decision snapshot service: %s", message)
        except Exception:
            pass
        if not self.fail_open:
            self.available = False


def _outcome_id(decision_id: str, alpha_id: str | None, data: dict[str, Any]) -> str:
    import hashlib

    seed = f"{decision_id}|{alpha_id or ''}|{data.get('created_at') or utc_now_iso()}"
    return "outcome:" + hashlib.sha256(seed.encode("utf-8", errors="replace")).hexdigest()[:24]


def _clean_dict(value: Any) -> dict[str, Any]:
    from wq_workflow.data.json_utils import to_jsonable

    cleaned = to_jsonable(value if isinstance(value, dict) else {})
    return cleaned if isinstance(cleaned, dict) else {}


def _pick_text(data: dict[str, Any], key: str) -> str | None:
    value = data.get(key)
    if value is None or value == "":
        return None
    return str(value)


def _pick_float(data: dict[str, Any], key: str) -> float | None:
    metrics = data.get("metrics") if isinstance(data.get("metrics"), dict) else {}
    value = data.get(key, metrics.get(key))
    if value is None or value == "":
        return None
    try:
        number = float(value)
        return number if number == number and number not in {float("inf"), float("-inf")} else None
    except Exception:
        return None


def _pick_bool(data: dict[str, Any], key: str) -> bool | None:
    value = data.get(key)
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on", "pass", "passed", "success"}:
        return True
    if text in {"0", "false", "no", "n", "off", "fail", "failed", "failure"}:
        return False
    return None


class OfflineReplayService:
    def __init__(
        self,
        *,
        config: Any | None = None,
        repository: ReplayRepository | None = None,
        reporter: ReplayReporter | None = None,
        dataset_loader: ReplayDatasetLoader | None = None,
        engine: ReplayEngine | None = None,
        storage: Any | None = None,
        db_path: str | Path | None = None,
        logger: Any | None = None,
    ) -> None:
        self.config = config
        self.logger = logger
        self.enabled = bool(getattr(config, "enable_offline_replay", False))
        self.auto_run = bool(getattr(config, "offline_replay_auto_run", False))
        self.mode = str(getattr(config, "offline_replay_mode", "advisory") or "advisory")
        self.fail_open = bool(getattr(config, "offline_replay_fail_open", True))
        self.repository = repository or ReplayRepository(storage=storage, db_path=db_path or getattr(config, "storage_db_path", None), logger=logger)
        self.dataset_loader = dataset_loader or ReplayDatasetLoader(storage=storage, db_path=db_path or getattr(config, "storage_db_path", None), logger=logger)
        status_path = getattr(config, "offline_replay_status_path", "runtime/status/offline_replay_report.json")
        self.reporter = reporter or ReplayReporter(repository=self.repository, status_path=status_path, logger=logger)
        self.engine = engine or ReplayEngine(
            dataset_loader=self.dataset_loader,
            repository=self.repository,
            reporter=self.reporter,
            config=config,
            storage=storage,
            db_path=str(db_path) if db_path is not None else None,
            logger=logger,
        )
        self.available = True
        self.warnings: list[str] = []

    def startup_check(self) -> dict[str, Any]:
        try:
            result = self.repository.initialize()
            if not result.get("ok", False):
                self.available = False
                self._warn(str(result.get("error") or getattr(self.repository, "last_error", "repository_initialize_failed")))
                return {"ok": False, "enabled": self.enabled, "available": False, "mode": self.mode, "warnings": list(self.warnings)}
            report = self.update_report()
            if self.enabled and self.auto_run:
                self.run_replay()
            return {"ok": True, "enabled": self.enabled, "available": True, "mode": self.mode, "auto_run": self.auto_run, "report": report, "warnings": list(self.warnings)}
        except Exception as exc:
            self.available = False
            self._warn(f"startup_check_failed: {exc}")
            return {"ok": False, "enabled": self.enabled, "available": False, "mode": self.mode, "warnings": list(self.warnings)}

    def run_replay(self, dataset_filter: ReplayDatasetFilter | dict[str, Any] | None = None, policies: list[Any] | None = None, name: str | None = None) -> ReplayRun:
        if not self.available:
            return ReplayRun(name=name or "offline_replay", status="failed", completed_at=utc_now_iso(), raw_payload={"error": "offline_replay_unavailable"})
        try:
            return self.engine.run_replay(dataset_filter=dataset_filter, policies=policies, name=name)
        except Exception as exc:
            self._warn(f"run_replay_failed: {exc}")
            return ReplayRun(name=name or "offline_replay", status="failed", completed_at=utc_now_iso(), raw_payload={"error": str(exc)})

    def get_latest_report(self) -> dict[str, Any]:
        path = Path(str(getattr(self.reporter, "status_path", "runtime/status/offline_replay_report.json")))
        try:
            if path.exists():
                import json

                data = json.loads(path.read_text(encoding="utf-8"))
                return data if isinstance(data, dict) else {}
        except Exception as exc:
            self._warn(f"get_latest_report_failed: {exc}")
        return self.update_report()

    def list_replay_runs(self) -> list[ReplayRun]:
        return self.repository.list_replay_runs()

    def update_report(self) -> dict[str, Any]:
        try:
            return self.reporter.update(enabled=self.enabled, mode=self.mode, warnings=list(self.warnings))
        except Exception as exc:
            self._warn(f"update_report_failed: {exc}")
            return {"ok": False, "enabled": self.enabled, "warnings": list(self.warnings)}

    def get_replay_evidence_summary(self) -> dict[str, Any]:
        try:
            runs = self.repository.list_replay_runs(limit=1)
            if not runs:
                return {"available": False, "latest_replay_run_id": "", "warnings": list(self.warnings)}
            run = runs[0]
            metrics = [item.to_dict() for item in self.repository.list_policy_metrics(run.replay_run_id)]
            comparisons = [item.to_dict() for item in self.repository.list_comparisons(run.replay_run_id)]
            return {"available": True, "latest_replay_run_id": run.replay_run_id, "status": run.status, "metrics": metrics, "comparisons": comparisons, "warnings": list(self.warnings)}
        except Exception as exc:
            self._warn(f"get_replay_evidence_summary_failed: {exc}")
            return {"available": False, "warnings": list(self.warnings)}

    def _warn(self, message: str) -> None:
        self.warnings.append(message)
        self.warnings = self.warnings[-50:]
        try:
            if self.logger is not None:
                self.logger.warning("offline replay service: %s", message)
        except Exception:
            pass
        if not self.fail_open:
            self.available = False



class CounterfactualService:
    def __init__(
        self,
        *,
        config: Any | None = None,
        repository: CounterfactualRepository | None = None,
        reporter: CounterfactualReporter | None = None,
        dataset_loader: CounterfactualDatasetLoader | None = None,
        evaluator: CounterfactualEvaluator | None = None,
        storage: Any | None = None,
        db_path: str | Path | None = None,
        logger: Any | None = None,
    ) -> None:
        self.config = config
        self.logger = logger
        self.enabled = bool(getattr(config, "enable_counterfactual_evaluation", False))
        self.auto_run = bool(getattr(config, "counterfactual_auto_run", False))
        self.mode = str(getattr(config, "counterfactual_mode", "advisory") or "advisory")
        self.fail_open = bool(getattr(config, "counterfactual_fail_open", True))
        self.repository = repository or CounterfactualRepository(storage=storage, db_path=db_path or getattr(config, "storage_db_path", None), logger=logger)
        self.dataset_loader = dataset_loader or CounterfactualDatasetLoader(storage=storage, db_path=db_path or getattr(config, "storage_db_path", None), config=config, logger=logger)
        status_path = getattr(config, "counterfactual_status_path", "runtime/status/counterfactual_report.json")
        self.reporter = reporter or CounterfactualReporter(repository=self.repository, status_path=status_path, logger=logger)
        self.evaluator = evaluator or CounterfactualEvaluator(
            dataset_loader=self.dataset_loader,
            repository=self.repository,
            reporter=self.reporter,
            config=config,
            storage=storage,
            db_path=str(db_path) if db_path is not None else None,
            logger=logger,
        )
        self.available = True
        self.warnings: list[str] = []

    def startup_check(self) -> dict[str, Any]:
        try:
            result = self.repository.initialize()
            if not result.get("ok", False):
                self.available = False
                self._warn(str(result.get("error") or getattr(self.repository, "last_error", "repository_initialize_failed")))
                return {"ok": False, "enabled": self.enabled, "available": False, "mode": self.mode, "warnings": list(self.warnings)}
            report = self.update_report()
            if self.enabled and self.auto_run:
                self.evaluate_replay_run(limit=int(getattr(self.config, "counterfactual_default_limit", 1000) or 1000))
            return {"ok": True, "enabled": self.enabled, "available": True, "mode": self.mode, "auto_run": self.auto_run, "report": report, "warnings": list(self.warnings)}
        except Exception as exc:
            self.available = False
            self._warn(f"startup_check_failed: {exc}")
            return {"ok": False, "enabled": self.enabled, "available": False, "mode": self.mode, "warnings": list(self.warnings)}

    def evaluate_request(self, request: CounterfactualRequest | dict[str, Any]) -> CounterfactualEstimate:
        if not self.available:
            return CounterfactualEstimate(verdict="insufficient_evidence", confidence="insufficient", reason_codes=["counterfactual_unavailable"], estimated_not_observed=True)
        try:
            return self.evaluator.evaluate_request(request)
        except Exception as exc:
            self._warn(f"evaluate_request_failed: {exc}")
            req = CounterfactualRequest.from_dict(request)
            return CounterfactualEstimate(request_id=req.request_id, decision_id=req.decision_id, verdict="insufficient_evidence", confidence="insufficient", reason_codes=["counterfactual_evaluation_failed"], estimated_not_observed=True)

    def evaluate_replay_run(self, replay_run_id: str | None = None, limit: int | None = None) -> list[CounterfactualEstimate]:
        if not self.available:
            return []
        try:
            return self.evaluator.evaluate_replay_run(replay_run_id=replay_run_id, limit=int(limit or getattr(self.config, "counterfactual_default_limit", 1000) or 1000))
        except Exception as exc:
            self._warn(f"evaluate_replay_run_failed: {exc}")
            return []

    def get_latest_report(self) -> dict[str, Any]:
        path = Path(str(getattr(self.reporter, "status_path", "runtime/status/counterfactual_report.json")))
        try:
            if path.exists():
                import json

                data = json.loads(path.read_text(encoding="utf-8"))
                return data if isinstance(data, dict) else {}
        except Exception as exc:
            self._warn(f"get_latest_report_failed: {exc}")
        return self.update_report()

    def get_counterfactual_evidence_summary(self) -> dict[str, Any]:
        try:
            summaries = [item.to_dict() for item in self.repository.list_summaries()]
            estimates = [item.to_dict() for item in self.repository.list_estimates(limit=20)]
            return {"available": self.available, "enabled": self.enabled, "mode": self.mode, "summaries": summaries, "recent_estimates": estimates, "warnings": list(self.warnings)}
        except Exception as exc:
            self._warn(f"get_counterfactual_evidence_summary_failed: {exc}")
            return {"available": False, "enabled": self.enabled, "warnings": list(self.warnings)}

    def update_report(self) -> dict[str, Any]:
        try:
            self.repository.update_summary(None)
            return self.reporter.update(enabled=self.enabled, mode=self.mode, warnings=list(self.warnings))
        except Exception as exc:
            self._warn(f"update_report_failed: {exc}")
            return {"ok": False, "enabled": self.enabled, "warnings": list(self.warnings)}

    def _warn(self, message: str) -> None:
        self.warnings.append(message)
        self.warnings = self.warnings[-50:]
        try:
            if self.logger is not None:
                self.logger.warning("counterfactual service: %s", message)
        except Exception:
            pass
        if not self.fail_open:
            self.available = False
