from __future__ import annotations

import hashlib
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from wq_workflow.data.json_utils import json_dumps_safe, json_loads_safe, safe_float
from wq_workflow.data.migrations import initialize_refactor_tables
from wq_workflow.storage.sqlite_store import connect_db

from .schema import DecisionAction, DecisionOutcome, DecisionSnapshot, DecisionSnapshotSummary, utc_now_iso


class DecisionSnapshotRepository:
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
            raise RuntimeError("decision snapshot database path unavailable")
        conn = connect_db(self.db_path)
        try:
            initialize_refactor_tables(conn)
            yield conn
        finally:
            conn.close()

    def initialize(self) -> dict[str, Any]:
        return self._safe(lambda: self._initialize(), default={"ok": False})

    def _initialize(self) -> dict[str, Any]:
        with self.connection() as conn:
            initialize_refactor_tables(conn)
            self._commit(conn)
        return {"ok": True}

    def save_snapshot(self, snapshot: DecisionSnapshot) -> dict[str, Any]:
        return self._safe(lambda: self._save_snapshot(snapshot), default={"ok": False, "decision_id": getattr(snapshot, "decision_id", "")})

    def _save_snapshot(self, snapshot: DecisionSnapshot) -> dict[str, Any]:
        snap = snapshot if isinstance(snapshot, DecisionSnapshot) else DecisionSnapshot.from_dict(snapshot)
        data = snap.to_dict()
        with self.connection() as conn:
            existing = conn.execute("SELECT created_at FROM decision_snapshots WHERE decision_id=?", (snap.decision_id,)).fetchone()
            created_at = snap.created_at or (existing["created_at"] if existing is not None and hasattr(existing, "keys") and "created_at" in existing.keys() else utc_now_iso())
            conn.execute(
                """
                INSERT INTO decision_snapshots
                (decision_id, decision_type, workflow_run_id, iteration, alpha_id, experiment_id, arm_id, budget_plan_id,
                 available_actions_json, chosen_action_json, legacy_choice_json, model_choice_json, experiment_choice_json,
                 governance_decision, features_json, scores_json, context_json, actual_result_json, reward,
                 platform_sc_status, platform_sc_abs_max, success, quality_passed, created_at, updated_at, raw_payload,
                 action_scores_json, selection_reason, legacy_score, model_score, propensity, model_version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(decision_id) DO UPDATE SET
                  decision_type=excluded.decision_type,
                  workflow_run_id=excluded.workflow_run_id,
                  iteration=excluded.iteration,
                  alpha_id=excluded.alpha_id,
                  experiment_id=excluded.experiment_id,
                  arm_id=excluded.arm_id,
                  budget_plan_id=excluded.budget_plan_id,
                  available_actions_json=excluded.available_actions_json,
                  chosen_action_json=excluded.chosen_action_json,
                  legacy_choice_json=excluded.legacy_choice_json,
                  model_choice_json=excluded.model_choice_json,
                  experiment_choice_json=excluded.experiment_choice_json,
                  governance_decision=excluded.governance_decision,
                  features_json=excluded.features_json,
                  scores_json=excluded.scores_json,
                  context_json=excluded.context_json,
                  actual_result_json=COALESCE(excluded.actual_result_json, decision_snapshots.actual_result_json),
                  reward=COALESCE(excluded.reward, decision_snapshots.reward),
                  platform_sc_status=COALESCE(excluded.platform_sc_status, decision_snapshots.platform_sc_status),
                  platform_sc_abs_max=COALESCE(excluded.platform_sc_abs_max, decision_snapshots.platform_sc_abs_max),
                  success=COALESCE(excluded.success, decision_snapshots.success),
                  quality_passed=COALESCE(excluded.quality_passed, decision_snapshots.quality_passed),
                  updated_at=excluded.updated_at,
                  raw_payload=excluded.raw_payload,
                  action_scores_json=excluded.action_scores_json
                """,
                (
                    snap.decision_id,
                    snap.decision_type,
                    snap.workflow_run_id,
                    snap.iteration,
                    snap.alpha_id,
                    snap.experiment_id,
                    snap.arm_id,
                    snap.budget_plan_id,
                    json_dumps_safe(data.get("available_actions") or []),
                    json_dumps_safe(data.get("chosen_action") or {}),
                    json_dumps_safe(data.get("legacy_choice") or {}),
                    json_dumps_safe(data.get("model_choice") or {}),
                    json_dumps_safe(data.get("experiment_choice") or {}),
                    snap.governance_decision,
                    json_dumps_safe(data.get("features") or {}),
                    json_dumps_safe(data.get("scores") or {}),
                    json_dumps_safe(data.get("context") or {}),
                    json_dumps_safe(data.get("actual_result")) if data.get("actual_result") is not None else None,
                    snap.reward,
                    snap.platform_sc_status,
                    snap.platform_sc_abs_max,
                    _bool_to_int(snap.success),
                    _bool_to_int(snap.quality_passed),
                    created_at,
                    snap.updated_at or utc_now_iso(),
                    json_dumps_safe(data.get("raw_payload") or {}),
                    json_dumps_safe(data.get("scores") or {}),
                    str((data.get("raw_payload") or {}).get("selection_reason") or ""),
                    _action_score(snap.legacy_choice),
                    _action_score(snap.model_choice),
                    safe_float((data.get("raw_payload") or {}).get("propensity")),
                    str(((data.get("model_choice") or {}).get("metadata") or {}).get("model_version") if isinstance(data.get("model_choice"), dict) else ""),
                ),
            )
            self._commit(conn)
        return {"ok": True, "decision_id": snap.decision_id}

    def get_snapshot(self, decision_id: str) -> DecisionSnapshot | None:
        return self._safe(lambda: self._get_snapshot(decision_id), default=None)

    def _get_snapshot(self, decision_id: str) -> DecisionSnapshot | None:
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM decision_snapshots WHERE decision_id=?", (decision_id,)).fetchone()
        return _snapshot_from_row(row)

    def list_snapshots(self, decision_type: str | None = None, alpha_id: str | None = None, limit: int = 500) -> list[DecisionSnapshot]:
        return self._safe(lambda: self._list_snapshots(decision_type=decision_type, alpha_id=alpha_id, limit=limit), default=[])

    def _list_snapshots(self, decision_type: str | None = None, alpha_id: str | None = None, limit: int = 500) -> list[DecisionSnapshot]:
        clauses: list[str] = []
        params: list[Any] = []
        if decision_type:
            clauses.append("decision_type=?")
            params.append(decision_type)
        if alpha_id:
            clauses.append("alpha_id=?")
            params.append(alpha_id)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        params.append(max(1, int(limit)))
        with self.connection() as conn:
            rows = conn.execute(f"SELECT * FROM decision_snapshots{where} ORDER BY created_at DESC LIMIT ?", tuple(params)).fetchall()
        return [item for item in (_snapshot_from_row(row) for row in rows) if item is not None]

    def save_outcome(self, outcome: DecisionOutcome) -> dict[str, Any]:
        return self._safe(lambda: self._save_outcome(outcome), default={"ok": False, "outcome_id": getattr(outcome, "outcome_id", "")})

    def _save_outcome(self, outcome: DecisionOutcome) -> dict[str, Any]:
        out = outcome if isinstance(outcome, DecisionOutcome) else DecisionOutcome.from_dict(outcome)
        if not out.outcome_id:
            out.outcome_id = _stable_outcome_id(out.decision_id, out.alpha_id, out.created_at)
        data = out.to_dict()
        with self.connection() as conn:
            decision_type = ""
            row = conn.execute("SELECT decision_type FROM decision_snapshots WHERE decision_id=?", (out.decision_id,)).fetchone()
            if row is not None and hasattr(row, "keys"):
                decision_type = str(row["decision_type"] or "")
            conn.execute(
                """
                INSERT OR REPLACE INTO decision_outcomes
                (outcome_id, decision_id, decision_type, alpha_id, success, reward, reward_delta, sharpe, fitness,
                 returns, turnover, drawdown, margin, platform_sc_status, platform_sc_abs_max,
                 quality_passed, failure_type, metrics_json, created_at, raw_payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    out.outcome_id,
                    out.decision_id,
                    decision_type,
                    out.alpha_id,
                    _bool_to_int(out.success),
                    out.reward,
                    safe_float(data.get("raw_payload", {}).get("reward_delta") if isinstance(data.get("raw_payload"), dict) else None),
                    out.sharpe,
                    out.fitness,
                    out.returns,
                    out.turnover,
                    out.drawdown,
                    out.margin,
                    out.platform_sc_status,
                    out.platform_sc_abs_max,
                    _bool_to_int(out.quality_passed),
                    out.failure_type,
                    json_dumps_safe({k: data.get(k) for k in ("sharpe", "fitness", "returns", "turnover", "drawdown", "margin")}),
                    out.created_at,
                    json_dumps_safe(data.get("raw_payload") or {}),
                ),
            )
            self._commit(conn)
        return {"ok": True, "outcome_id": out.outcome_id}

    def get_outcomes_for_decision(self, decision_id: str) -> list[DecisionOutcome]:
        return self._safe(lambda: self._get_outcomes_for_decision(decision_id), default=[])

    def _get_outcomes_for_decision(self, decision_id: str) -> list[DecisionOutcome]:
        with self.connection() as conn:
            rows = conn.execute("SELECT * FROM decision_outcomes WHERE decision_id=? ORDER BY created_at DESC", (decision_id,)).fetchall()
        return [item for item in (_outcome_from_row(row) for row in rows) if item is not None]

    def find_snapshots_by_alpha(self, alpha_id: str) -> list[DecisionSnapshot]:
        if not alpha_id:
            return []
        return self.list_snapshots(alpha_id=alpha_id, limit=5000)

    def update_snapshot_outcome(self, decision_id: str, outcome_context: dict[str, Any]) -> dict[str, Any]:
        return self._safe(lambda: self._update_snapshot_outcome(decision_id, outcome_context), default={"ok": False})

    def _update_snapshot_outcome(self, decision_id: str, outcome_context: dict[str, Any]) -> dict[str, Any]:
        data = outcome_context if isinstance(outcome_context, dict) else {}
        now = utc_now_iso()
        with self.connection() as conn:
            conn.execute(
                """
                UPDATE decision_snapshots
                SET actual_result_json=?, reward=?, platform_sc_status=?, platform_sc_abs_max=?,
                    success=?, quality_passed=?, updated_at=?
                WHERE decision_id=?
                """,
                (
                    json_dumps_safe(data),
                    safe_float(data.get("reward")),
                    data.get("platform_sc_status"),
                    safe_float(data.get("platform_sc_abs_max")),
                    _bool_to_int(data.get("success")),
                    _bool_to_int(data.get("quality_passed")),
                    now,
                    decision_id,
                ),
            )
            self._commit(conn)
        return {"ok": True, "decision_id": decision_id}

    def update_summary(self, decision_type: str) -> DecisionSnapshotSummary | None:
        return self._safe(lambda: self._update_summary(decision_type), default=None)

    def _update_summary(self, decision_type: str) -> DecisionSnapshotSummary:
        with self.connection() as conn:
            snapshots = conn.execute("SELECT decision_id FROM decision_snapshots WHERE decision_type=?", (decision_type,)).fetchall()
            outcomes = conn.execute(
                """
                SELECT o.* FROM decision_outcomes o
                JOIN decision_snapshots s ON s.decision_id=o.decision_id
                WHERE s.decision_type=?
                """,
                (decision_type,),
            ).fetchall()
            rewards = [safe_float(row["reward"]) for row in outcomes if hasattr(row, "keys") and safe_float(row["reward"]) is not None]
            sc_values = [safe_float(row["platform_sc_abs_max"]) for row in outcomes if hasattr(row, "keys") and safe_float(row["platform_sc_abs_max"]) is not None]
            success_count = sum(1 for row in outcomes if hasattr(row, "keys") and row["success"] == 1)
            summary = DecisionSnapshotSummary(
                decision_type=decision_type,
                sample_count=len(snapshots),
                outcome_count=len(outcomes),
                success_count=success_count,
                avg_reward=(sum(rewards) / len(rewards)) if rewards else None,
                avg_platform_sc_abs_max=(sum(sc_values) / len(sc_values)) if sc_values else None,
                updated_at=utc_now_iso(),
                raw_payload={"phase": "5A", "tracking_only": True},
            )
            conn.execute(
                """
                INSERT OR REPLACE INTO decision_snapshot_summaries
                (summary_id, decision_type, sample_count, outcome_count, success_count,
                 avg_reward, avg_platform_sc_abs_max, updated_at, raw_payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"summary:{decision_type}",
                    summary.decision_type,
                    summary.sample_count,
                    summary.outcome_count,
                    summary.success_count,
                    summary.avg_reward,
                    summary.avg_platform_sc_abs_max,
                    summary.updated_at,
                    json_dumps_safe(summary.raw_payload),
                ),
            )
            self._commit(conn)
        return summary

    def list_summaries(self) -> list[DecisionSnapshotSummary]:
        return self._safe(lambda: self._list_summaries(), default=[])

    def _list_summaries(self) -> list[DecisionSnapshotSummary]:
        with self.connection() as conn:
            rows = conn.execute("SELECT * FROM decision_snapshot_summaries ORDER BY decision_type").fetchall()
        return [item for item in (_summary_from_row(row) for row in rows) if item is not None]

    def count_snapshots(self) -> int:
        return int(self._safe(lambda: self._count("decision_snapshots"), default=0) or 0)

    def count_outcomes(self) -> int:
        return int(self._safe(lambda: self._count("decision_outcomes"), default=0) or 0)

    def _count(self, table: str) -> int:
        with self.connection() as conn:
            row = conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
        return int(row["n"] if row is not None and hasattr(row, "keys") else 0)

    def _safe(self, call: Any, default: Any = None) -> Any:
        try:
            self.last_error = ""
            return call()
        except Exception as exc:
            self.last_error = str(exc)
            try:
                if self.logger is not None:
                    self.logger.warning("decision snapshot repository failure: %s", exc)
            except Exception:
                pass
            return default

    def _commit(self, conn: sqlite3.Connection) -> None:
        try:
            conn.commit()
        except Exception:
            pass


def _snapshot_from_row(row: Any) -> DecisionSnapshot | None:
    if row is None or not hasattr(row, "keys"):
        return None
    data = dict(row)
    scores = json_loads_safe(data.get("scores_json") or data.get("action_scores_json"), {})
    return DecisionSnapshot.from_dict(
        {
            "decision_id": data.get("decision_id"),
            "decision_type": data.get("decision_type"),
            "workflow_run_id": data.get("workflow_run_id"),
            "iteration": data.get("iteration"),
            "alpha_id": data.get("alpha_id"),
            "experiment_id": data.get("experiment_id"),
            "arm_id": data.get("arm_id"),
            "budget_plan_id": data.get("budget_plan_id"),
            "available_actions": json_loads_safe(data.get("available_actions_json"), []),
            "chosen_action": json_loads_safe(data.get("chosen_action_json"), None),
            "legacy_choice": json_loads_safe(data.get("legacy_choice_json"), None),
            "model_choice": json_loads_safe(data.get("model_choice_json"), None),
            "experiment_choice": json_loads_safe(data.get("experiment_choice_json"), None),
            "governance_decision": data.get("governance_decision"),
            "features": json_loads_safe(data.get("features_json"), {}),
            "scores": scores,
            "context": json_loads_safe(data.get("context_json"), {}),
            "actual_result": json_loads_safe(data.get("actual_result_json"), None),
            "reward": data.get("reward"),
            "platform_sc_status": data.get("platform_sc_status"),
            "platform_sc_abs_max": data.get("platform_sc_abs_max"),
            "success": data.get("success"),
            "quality_passed": data.get("quality_passed"),
            "created_at": data.get("created_at"),
            "updated_at": data.get("updated_at") or data.get("created_at"),
            "raw_payload": json_loads_safe(data.get("raw_payload"), {}),
        }
    )


def _outcome_from_row(row: Any) -> DecisionOutcome | None:
    if row is None or not hasattr(row, "keys"):
        return None
    data = dict(row)
    metrics = json_loads_safe(data.get("metrics_json"), {})
    payload = json_loads_safe(data.get("raw_payload"), {})
    if isinstance(payload, dict) and isinstance(metrics, dict):
        payload.setdefault("metrics", metrics)
    return DecisionOutcome.from_dict(
        {
            "outcome_id": data.get("outcome_id"),
            "decision_id": data.get("decision_id"),
            "alpha_id": data.get("alpha_id"),
            "success": data.get("success"),
            "reward": data.get("reward"),
            "sharpe": data.get("sharpe", metrics.get("sharpe") if isinstance(metrics, dict) else None),
            "fitness": data.get("fitness", metrics.get("fitness") if isinstance(metrics, dict) else None),
            "returns": data.get("returns", metrics.get("returns") if isinstance(metrics, dict) else None),
            "turnover": data.get("turnover", metrics.get("turnover") if isinstance(metrics, dict) else None),
            "drawdown": data.get("drawdown", metrics.get("drawdown") if isinstance(metrics, dict) else None),
            "margin": data.get("margin", metrics.get("margin") if isinstance(metrics, dict) else None),
            "platform_sc_status": data.get("platform_sc_status"),
            "platform_sc_abs_max": data.get("platform_sc_abs_max"),
            "quality_passed": data.get("quality_passed"),
            "failure_type": data.get("failure_type"),
            "created_at": data.get("created_at"),
            "raw_payload": payload if isinstance(payload, dict) else {},
        }
    )


def _summary_from_row(row: Any) -> DecisionSnapshotSummary | None:
    if row is None or not hasattr(row, "keys"):
        return None
    data = dict(row)
    return DecisionSnapshotSummary.from_dict(
        {
            "decision_type": data.get("decision_type"),
            "sample_count": data.get("sample_count"),
            "outcome_count": data.get("outcome_count"),
            "success_count": data.get("success_count"),
            "avg_reward": data.get("avg_reward"),
            "avg_platform_sc_abs_max": data.get("avg_platform_sc_abs_max"),
            "updated_at": data.get("updated_at"),
            "raw_payload": json_loads_safe(data.get("raw_payload"), {}),
        }
    )


def _bool_to_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, (int, float)):
        return 1 if value else 0
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on", "pass", "passed", "success"}:
        return 1
    if text in {"0", "false", "no", "n", "off", "fail", "failed", "failure"}:
        return 0
    return None


def _stable_outcome_id(decision_id: str, alpha_id: str | None, created_at: str) -> str:
    seed = f"{decision_id}|{alpha_id or ''}|{created_at}"
    digest = hashlib.sha256(seed.encode("utf-8", errors="replace")).hexdigest()[:24]
    return f"outcome:{digest}"


def _action_score(action: DecisionAction | None) -> float | None:
    return action.score if isinstance(action, DecisionAction) else None
