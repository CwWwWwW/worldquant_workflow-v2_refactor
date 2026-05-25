from __future__ import annotations

import hashlib
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from wq_workflow.data.migrations import initialize_refactor_tables
from wq_workflow.storage.sqlite_store import connect_db

from .replay_dataset import ReplayDatasetLoader
from .replay_repository import ReplayRepository, _decision_from_row
from .schema import CounterfactualRequest, DecisionAction, ReplayDatasetFilter, ReplayPolicyDecision, ReplayRecord, utc_now_iso


class CounterfactualDatasetLoader:
    def __init__(
        self,
        conn: sqlite3.Connection | None = None,
        *,
        storage: Any | None = None,
        db_path: str | Path | None = None,
        replay_loader: ReplayDatasetLoader | None = None,
        replay_repository: ReplayRepository | None = None,
        config: Any | None = None,
        logger: Any | None = None,
    ) -> None:
        self.conn = conn
        self.storage = storage
        path = db_path if db_path is not None else getattr(getattr(storage, "config", None), "db_path", None)
        self.db_path = Path(path) if path is not None else None
        self.config = config
        self.logger = logger
        self.last_error = ""
        self.replay_loader = replay_loader or ReplayDatasetLoader(conn=conn, storage=storage, db_path=self.db_path, logger=logger)
        self.replay_repository = replay_repository or ReplayRepository(conn=conn, storage=storage, db_path=self.db_path, logger=logger)

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        if self.conn is not None:
            self.conn.row_factory = sqlite3.Row
            initialize_refactor_tables(self.conn)
            yield self.conn
            return
        if self.db_path is None:
            raise RuntimeError("counterfactual database path unavailable")
        conn = connect_db(self.db_path)
        try:
            initialize_refactor_tables(conn)
            yield conn
        finally:
            conn.close()

    def load_observed_records(self, decision_type: str | None = None, limit: int = 5000) -> list[ReplayRecord]:
        try:
            filt = ReplayDatasetFilter(decision_types=[decision_type] if decision_type else [], require_outcome=True, raw_payload={"limit": max(1, int(limit))})
            return [record for record in self.replay_loader.load_records(filt) if _has_observed_outcome(record)]
        except Exception as exc:
            self._warn(f"load_observed_records_failed: {exc}")
            return []

    def load_candidate_evidence(self, request: CounterfactualRequest, limit: int = 500) -> list[ReplayRecord]:
        req = CounterfactualRequest.from_dict(request)
        return self.load_observed_records(decision_type=req.decision_type, limit=limit)

    def load_replay_policy_decisions(self, replay_run_id: str | None = None, only_insufficient: bool = True, limit: int = 1000) -> list[ReplayPolicyDecision]:
        try:
            if replay_run_id:
                decisions = self.replay_repository.list_policy_decisions(replay_run_id)
            else:
                decisions = self._list_recent_policy_decisions(limit=limit)
            out: list[ReplayPolicyDecision] = []
            for decision in decisions:
                item = ReplayPolicyDecision.from_dict(decision)
                if only_insufficient and "insufficient_counterfactual_evidence" not in set(item.reason_codes or []):
                    continue
                out.append(item)
                if len(out) >= max(1, int(limit)):
                    break
            return out
        except Exception as exc:
            self._warn(f"load_replay_policy_decisions_failed: {exc}")
            return []

    def load_record_for_decision(self, decision_id: str) -> ReplayRecord | None:
        try:
            records = self.replay_loader.load_records(ReplayDatasetFilter(raw_payload={"limit": 1, "decision_id": decision_id}))
            for record in records:
                if record.decision_id == decision_id:
                    return record
            with self.replay_loader.connection() as conn:
                from .repository import _snapshot_from_row
                row = conn.execute("SELECT * FROM decision_snapshots WHERE decision_id=?", (decision_id,)).fetchone()
                snap = _snapshot_from_row(row)
            if snap is None:
                return None
            outcomes = self.replay_loader._load_outcomes(decision_id)  # existing loader method, read-only
            return self.replay_loader.build_record(snap, outcomes)
        except Exception as exc:
            self._warn(f"load_record_for_decision_failed: {exc}")
            return None

    def build_request_from_policy_decision(self, policy_decision: ReplayPolicyDecision | dict[str, Any], replay_record: ReplayRecord | dict[str, Any] | None) -> CounterfactualRequest | None:
        decision = ReplayPolicyDecision.from_dict(policy_decision)
        if decision.observable_outcome:
            return None
        if decision.selected_action is None:
            return None
        record = ReplayRecord.from_dict(replay_record or {})
        actual = record.chosen_action if record.chosen_action is not None else None
        selected = DecisionAction.from_dict(decision.selected_action)
        if actual is not None:
            actual_action = DecisionAction.from_dict(actual)
            if selected.action_id and selected.action_id == actual_action.action_id and selected.action_type == actual_action.action_type:
                return None
        decision_type = record.decision_type or str((decision.raw_payload or {}).get("decision_type") or "unknown")
        min_evidence = int(getattr(self.config, "counterfactual_min_evidence", 30) or 30)
        request = CounterfactualRequest(
            request_id=_request_id(decision.replay_run_id, decision.policy_decision_id, decision.decision_id, selected.to_dict()),
            replay_run_id=decision.replay_run_id or None,
            policy_decision_id=decision.policy_decision_id or None,
            decision_id=decision.decision_id,
            decision_type=decision_type,
            target_action=selected,
            actual_action=actual,
            alpha_id=record.alpha_id or (decision.raw_payload or {}).get("alpha_id"),
            experiment_id=record.experiment_id,
            arm_id=record.arm_id,
            budget_plan_id=record.budget_plan_id,
            features=dict(record.features or {}),
            context=dict(record.context or {}),
            min_evidence=min_evidence,
            created_at=utc_now_iso(),
            raw_payload={"policy_name": decision.policy_name, "reason_codes": list(decision.reason_codes or []), "record_id": record.record_id},
        )
        return request

    def _list_recent_policy_decisions(self, limit: int = 1000) -> list[ReplayPolicyDecision]:
        with self.connection() as conn:
            rows = conn.execute("SELECT * FROM offline_replay_policy_decisions ORDER BY created_at DESC LIMIT ?", (max(1, int(limit)),)).fetchall()
        return [item for item in (_decision_from_row(row) for row in rows) if item is not None]

    def _warn(self, message: str) -> None:
        self.last_error = message
        try:
            if self.logger is not None:
                self.logger.warning("counterfactual dataset: %s", message)
        except Exception:
            pass


def _has_observed_outcome(record: ReplayRecord) -> bool:
    item = ReplayRecord.from_dict(record)
    return item.outcome is not None and any(value is not None for value in (item.reward, item.success, item.platform_sc_abs_max, item.quality_passed))


def _request_id(replay_run_id: str, policy_decision_id: str, decision_id: str, action: dict[str, Any]) -> str:
    seed = f"{replay_run_id}|{policy_decision_id}|{decision_id}|{action}"
    return "counterfactual_request:" + hashlib.sha256(seed.encode("utf-8", errors="replace")).hexdigest()[:24]
