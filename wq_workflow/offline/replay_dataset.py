from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from wq_workflow.data.migrations import initialize_refactor_tables
from wq_workflow.storage.sqlite_store import connect_db

from .repository import _outcome_from_row, _snapshot_from_row
from .schema import DecisionAction, DecisionOutcome, DecisionSnapshot, ReplayDatasetFilter, ReplayRecord


class ReplayDatasetLoader:
    def __init__(self, conn: sqlite3.Connection | None = None, *, storage: Any | None = None, db_path: str | Path | None = None, logger: Any | None = None) -> None:
        self.conn = conn
        self.storage = storage
        path = db_path if db_path is not None else getattr(getattr(storage, "config", None), "db_path", None)
        self.db_path = Path(path) if path is not None else None
        self.logger = logger
        self.last_error = ""

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        if self.conn is not None:
            self.conn.row_factory = sqlite3.Row
            initialize_refactor_tables(self.conn)
            yield self.conn
            return
        if self.db_path is None:
            raise RuntimeError("offline replay database path unavailable")
        conn = connect_db(self.db_path)
        try:
            initialize_refactor_tables(conn)
            yield conn
        finally:
            conn.close()

    def load_records(self, dataset_filter: ReplayDatasetFilter | dict[str, Any] | None = None) -> list[ReplayRecord]:
        try:
            filt = ReplayDatasetFilter.from_dict(dataset_filter or {})
            snapshots = self._load_snapshots(filt)
            records: list[ReplayRecord] = []
            for snapshot in snapshots:
                outcomes = self._load_outcomes(snapshot.decision_id)
                record = self.build_record(snapshot, outcomes)
                if filt.require_outcome and record.outcome is None:
                    continue
                records.append(record)
            return records
        except Exception as exc:
            self._warn(f"load_records_failed: {exc}")
            return []

    def load_by_decision_type(self, decision_type: str, limit: int = 1000) -> list[ReplayRecord]:
        return self.load_records(ReplayDatasetFilter(decision_types=[decision_type], raw_payload={"limit": max(1, int(limit))}))

    def load_recent(self, limit: int = 1000) -> list[ReplayRecord]:
        return self.load_records(ReplayDatasetFilter(raw_payload={"limit": max(1, int(limit))}))

    def build_record(self, snapshot: DecisionSnapshot | dict[str, Any], outcomes: list[DecisionOutcome] | None = None) -> ReplayRecord:
        snap = DecisionSnapshot.from_dict(snapshot)
        outcome = (outcomes or [None])[0]
        if outcome is None and (snap.actual_result is not None or snap.reward is not None or snap.success is not None):
            outcome = DecisionOutcome(
                decision_id=snap.decision_id,
                alpha_id=snap.alpha_id,
                reward=snap.reward,
                success=snap.success,
                platform_sc_status=snap.platform_sc_status,
                platform_sc_abs_max=snap.platform_sc_abs_max,
                quality_passed=snap.quality_passed,
                raw_payload=snap.actual_result or {},
            )
        budget_choice = _extract_budget_choice(snap)
        return ReplayRecord(
            record_id=snap.decision_id,
            decision_id=snap.decision_id,
            decision_type=snap.decision_type,
            alpha_id=snap.alpha_id or (outcome.alpha_id if outcome else None),
            experiment_id=snap.experiment_id,
            arm_id=snap.arm_id,
            budget_plan_id=snap.budget_plan_id,
            available_actions=list(snap.available_actions or []),
            chosen_action=snap.chosen_action,
            legacy_choice=snap.legacy_choice,
            model_choice=snap.model_choice,
            experiment_choice=snap.experiment_choice,
            budget_choice=budget_choice,
            features=dict(snap.features or {}),
            scores=dict(snap.scores or {}),
            context=dict(snap.context or {}),
            outcome=outcome,
            reward=outcome.reward if outcome is not None else None,
            success=outcome.success if outcome is not None else None,
            platform_sc_abs_max=outcome.platform_sc_abs_max if outcome is not None else None,
            quality_passed=outcome.quality_passed if outcome is not None else None,
            created_at=snap.created_at,
            raw_payload={**dict(snap.raw_payload or {}), "snapshot": snap.to_dict(), "outcome_count": len(outcomes or [])},
        )

    def _load_snapshots(self, filt: ReplayDatasetFilter) -> list[DecisionSnapshot]:
        clauses: list[str] = []
        params: list[Any] = []
        if filt.decision_types:
            placeholders = ",".join("?" for _ in filt.decision_types)
            clauses.append(f"decision_type IN ({placeholders})")
            params.extend([str(item) for item in filt.decision_types])
        if filt.start_time:
            clauses.append("created_at>=?")
            params.append(filt.start_time)
        if filt.end_time:
            clauses.append("created_at<=?")
            params.append(filt.end_time)
        if filt.experiment_id:
            clauses.append("experiment_id=?")
            params.append(filt.experiment_id)
        if filt.arm_id:
            clauses.append("arm_id=?")
            params.append(filt.arm_id)
        if filt.budget_plan_id:
            clauses.append("budget_plan_id=?")
            params.append(filt.budget_plan_id)
        if filt.require_outcome:
            clauses.append("decision_id IN (SELECT decision_id FROM decision_outcomes)")
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        limit = int((filt.raw_payload or {}).get("limit") or 1000)
        limit = max(1, min(limit, 100000))
        with self.connection() as conn:
            rows = conn.execute(f"SELECT * FROM decision_snapshots{where} ORDER BY created_at DESC LIMIT ?", tuple(params + [limit])).fetchall()
        return [item for item in (_snapshot_from_row(row) for row in rows) if item is not None]

    def _load_outcomes(self, decision_id: str) -> list[DecisionOutcome]:
        with self.connection() as conn:
            rows = conn.execute("SELECT * FROM decision_outcomes WHERE decision_id=? ORDER BY created_at DESC", (decision_id,)).fetchall()
        return [item for item in (_outcome_from_row(row) for row in rows) if item is not None]

    def _warn(self, message: str) -> None:
        self.last_error = message
        try:
            if self.logger is not None:
                self.logger.warning("offline replay dataset: %s", message)
        except Exception:
            pass


def _extract_budget_choice(snapshot: DecisionSnapshot) -> DecisionAction | None:
    for source in (snapshot.context or {}, snapshot.raw_payload or {}):
        for key in ("budget_choice", "budget_action", "budget_recommendation"):
            if isinstance(source, dict) and source.get(key):
                return DecisionAction.from_dict(source.get(key))
    if snapshot.budget_plan_id:
        for action in snapshot.available_actions:
            item = DecisionAction.from_dict(action)
            if item.action_id == snapshot.budget_plan_id or item.metadata.get("budget_plan_id") == snapshot.budget_plan_id:
                return item
    return None
