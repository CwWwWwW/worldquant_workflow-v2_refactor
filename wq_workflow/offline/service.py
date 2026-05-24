from __future__ import annotations

from pathlib import Path
from typing import Any

from .decision_snapshot import DecisionSnapshotBuilder
from .repository import DecisionSnapshotRepository
from .reporter import DecisionSnapshotReporter
from .schema import DecisionOutcome, DecisionSnapshot, utc_now_iso


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
