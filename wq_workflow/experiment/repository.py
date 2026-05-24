from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from wq_workflow.data.json_utils import json_dumps_safe, json_loads_safe, safe_float, safe_int
from wq_workflow.data.migrations import initialize_refactor_tables
from wq_workflow.storage.sqlite_store import connect_db

from .budget import ExperimentBudgetPlan, ExperimentBudgetSnapshot
from .schema import ExperimentAssignment, ExperimentPlan, ExperimentResult, ExperimentSummary, utc_now_iso


class ExperimentRepository:
    def __init__(self, conn: sqlite3.Connection | None = None, *, storage: Any | None = None, db_path: str | Path | None = None, logger: Any | None = None) -> None:
        self.conn = conn
        self.storage = storage
        self.db_path = Path(db_path) if db_path is not None else self._db_path_from_storage(storage)
        self.logger = logger
        self.last_error: str = ""

    def _db_path_from_storage(self, storage: Any | None) -> Path | None:
        path = getattr(getattr(storage, "config", None), "db_path", None)
        return Path(path) if path is not None else None

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        if self.conn is not None:
            self.conn.row_factory = sqlite3.Row
            initialize_refactor_tables(self.conn)
            yield self.conn
            return
        if self.db_path is None:
            raise RuntimeError("experiment database path unavailable")
        conn = connect_db(self.db_path)
        try:
            initialize_refactor_tables(conn)
            yield conn
        finally:
            conn.close()

    def initialize(self) -> dict[str, Any]:
        return self._safe_write(lambda: self._initialize())

    def _initialize(self) -> None:
        with self.connection() as conn:
            initialize_refactor_tables(conn)
            self._commit(conn)

    def save_plan(self, plan: ExperimentPlan) -> dict[str, Any]:
        return self._safe_write(lambda: self._save_plan(plan), plan_id=plan.experiment_id)

    def _save_plan(self, plan: ExperimentPlan) -> None:
        data = plan.to_dict()
        with self.connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO experiment_plans
                (experiment_id, name, status, hypothesis_json, arms_json, created_at, updated_at, raw_payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    plan.experiment_id,
                    plan.name,
                    plan.status,
                    json_dumps_safe(data.get("hypothesis") or {}),
                    json_dumps_safe(data.get("arms") or []),
                    plan.created_at,
                    plan.updated_at,
                    json_dumps_safe(data.get("raw_payload") or {}),
                ),
            )
            self._commit(conn)

    def get_plan(self, experiment_id: str) -> ExperimentPlan | None:
        try:
            with self.connection() as conn:
                row = conn.execute("SELECT * FROM experiment_plans WHERE experiment_id=?", (experiment_id,)).fetchone()
            return self._plan_from_row(row)
        except Exception as exc:
            self._record_error(exc)
            return None

    def get_active_plans(self) -> list[ExperimentPlan]:
        try:
            with self.connection() as conn:
                rows = conn.execute("SELECT * FROM experiment_plans WHERE status='active' ORDER BY created_at DESC").fetchall()
            return [plan for plan in (self._plan_from_row(row) for row in rows) if plan is not None]
        except Exception as exc:
            self._record_error(exc)
            return []

    def save_assignment(self, assignment: ExperimentAssignment) -> dict[str, Any]:
        return self._safe_write(lambda: self._save_assignment(assignment), assignment_id=assignment.assignment_id)

    def _save_assignment(self, assignment: ExperimentAssignment) -> None:
        data = assignment.to_dict()
        with self.connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO experiment_assignments
                (assignment_id, experiment_id, arm_id, alpha_id, expression_hash, template_name,
                 template_family, operator_family, mutation_type, field_family, behavior_family,
                 assigned_by, created_at, raw_payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    assignment.assignment_id,
                    assignment.experiment_id,
                    assignment.arm_id,
                    assignment.alpha_id,
                    assignment.expression_hash,
                    assignment.template_name,
                    assignment.template_family,
                    assignment.operator_family,
                    assignment.mutation_type,
                    assignment.field_family,
                    assignment.behavior_family,
                    assignment.assigned_by,
                    assignment.created_at,
                    json_dumps_safe(data.get("raw_payload") or data),
                ),
            )
            self._commit(conn)

    def get_assignment(self, assignment_id: str) -> ExperimentAssignment | None:
        try:
            with self.connection() as conn:
                row = conn.execute("SELECT * FROM experiment_assignments WHERE assignment_id=?", (assignment_id,)).fetchone()
            return self._assignment_from_row(row)
        except Exception as exc:
            self._record_error(exc)
            return None

    def find_assignment_by_alpha(self, alpha_id: str) -> ExperimentAssignment | None:
        if not alpha_id:
            return None
        try:
            with self.connection() as conn:
                row = conn.execute(
                    "SELECT * FROM experiment_assignments WHERE alpha_id=? ORDER BY created_at DESC LIMIT 1",
                    (alpha_id,),
                ).fetchone()
            return self._assignment_from_row(row)
        except Exception as exc:
            self._record_error(exc)
            return None

    def save_result(self, result: ExperimentResult) -> dict[str, Any]:
        return self._safe_write(lambda: self._save_result(result), result_id=result.result_id)

    def _save_result(self, result: ExperimentResult) -> None:
        data = result.to_dict()
        with self.connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO experiment_results
                (result_id, assignment_id, experiment_id, arm_id, alpha_id, success, reward, sharpe,
                 fitness, returns, turnover, drawdown, margin, platform_sc_status,
                 platform_sc_abs_max, quality_passed, failure_type, created_at, raw_payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result.result_id,
                    result.assignment_id,
                    result.experiment_id,
                    result.arm_id,
                    result.alpha_id,
                    _bool_to_int(result.success),
                    result.reward,
                    result.sharpe,
                    result.fitness,
                    result.returns,
                    result.turnover,
                    result.drawdown,
                    result.margin,
                    result.platform_sc_status,
                    result.platform_sc_abs_max,
                    _bool_to_int(result.quality_passed),
                    result.failure_type,
                    result.created_at,
                    json_dumps_safe(data.get("raw_payload") or data),
                ),
            )
            self._commit(conn)

    def list_results(self, experiment_id: str, arm_id: str | None = None, limit: int = 500) -> list[ExperimentResult]:
        try:
            with self.connection() as conn:
                if arm_id:
                    rows = conn.execute(
                        "SELECT * FROM experiment_results WHERE experiment_id=? AND arm_id=? ORDER BY created_at DESC LIMIT ?",
                        (experiment_id, arm_id, max(1, int(limit))),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT * FROM experiment_results WHERE experiment_id=? ORDER BY created_at DESC LIMIT ?",
                        (experiment_id, max(1, int(limit))),
                    ).fetchall()
            return [result for result in (self._result_from_row(row) for row in rows) if result is not None]
        except Exception as exc:
            self._record_error(exc)
            return []

    def update_summary(self, experiment_id: str, arm_id: str) -> ExperimentSummary | None:
        try:
            summary = self._compute_summary(experiment_id, arm_id)
            with self.connection() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO experiment_summaries
                    (summary_id, experiment_id, arm_id, sample_count, success_count, failure_count,
                     avg_reward, avg_sharpe, avg_fitness, avg_platform_sc_abs_max,
                     quality_pass_rate, updated_at, raw_payload)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        f"{experiment_id}:{arm_id}",
                        summary.experiment_id,
                        summary.arm_id,
                        summary.sample_count,
                        summary.success_count,
                        summary.failure_count,
                        summary.avg_reward,
                        summary.avg_sharpe,
                        summary.avg_fitness,
                        summary.avg_platform_sc_abs_max,
                        summary.quality_pass_rate,
                        summary.updated_at,
                        json_dumps_safe(summary.raw_payload),
                    ),
                )
                self._commit(conn)
            return summary
        except Exception as exc:
            self._record_error(exc)
            return None

    def list_summaries(self, experiment_id: str | None = None) -> list[ExperimentSummary]:
        try:
            with self.connection() as conn:
                if experiment_id:
                    rows = conn.execute(
                        "SELECT * FROM experiment_summaries WHERE experiment_id=? ORDER BY updated_at DESC",
                        (experiment_id,),
                    ).fetchall()
                else:
                    rows = conn.execute("SELECT * FROM experiment_summaries ORDER BY updated_at DESC").fetchall()
            return [summary for summary in (self._summary_from_row(row) for row in rows) if summary is not None]
        except Exception as exc:
            self._record_error(exc)
            return []

    def save_budget_plan(self, plan: ExperimentBudgetPlan) -> dict[str, Any]:
        return self._safe_write(lambda: self._save_budget_plan(plan), budget_plan_id=plan.budget_plan_id)

    def _save_budget_plan(self, plan: ExperimentBudgetPlan) -> None:
        data = plan.to_dict()
        allocations = data.get("allocations") or []
        with self.connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO experiment_budget_plans
                (budget_plan_id, experiment_id, status, total_budget_hint, allocations_json,
                 generated_by, created_at, updated_at, raw_payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    plan.budget_plan_id,
                    plan.experiment_id,
                    plan.status,
                    plan.total_budget_hint,
                    json_dumps_safe(allocations),
                    plan.generated_by,
                    plan.created_at,
                    plan.updated_at,
                    json_dumps_safe(data.get("raw_payload") or {}),
                ),
            )
            for allocation in plan.allocations:
                alloc = allocation.to_dict()
                conn.execute(
                    """
                    INSERT OR REPLACE INTO experiment_budget_allocations
                    (allocation_id, budget_plan_id, experiment_id, arm_id, suggested_ratio, min_ratio,
                     max_ratio, sample_count, success_count, failure_count, avg_reward,
                     avg_platform_sc_abs_max, quality_pass_rate, reason_codes_json,
                     governance_allowed, status, created_at, raw_payload)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        allocation.allocation_id,
                        plan.budget_plan_id,
                        allocation.experiment_id,
                        allocation.arm_id,
                        allocation.suggested_ratio,
                        allocation.min_ratio,
                        allocation.max_ratio,
                        allocation.sample_count,
                        allocation.success_count,
                        allocation.failure_count,
                        allocation.avg_reward,
                        allocation.avg_platform_sc_abs_max,
                        allocation.quality_pass_rate,
                        json_dumps_safe(alloc.get("reason_codes") or []),
                        _bool_to_int(allocation.governance_allowed),
                        allocation.status,
                        allocation.created_at,
                        json_dumps_safe(alloc.get("raw_payload") or {}),
                    ),
                )
            self._commit(conn)

    def get_latest_budget_plan(self, experiment_id: str) -> ExperimentBudgetPlan | None:
        try:
            with self.connection() as conn:
                row = conn.execute(
                    "SELECT * FROM experiment_budget_plans WHERE experiment_id=? ORDER BY updated_at DESC, created_at DESC LIMIT 1",
                    (experiment_id,),
                ).fetchone()
            return self._budget_plan_from_row(row)
        except Exception as exc:
            self._record_error(exc)
            return None

    def list_budget_plans(self, experiment_id: str | None = None, limit: int = 20) -> list[ExperimentBudgetPlan]:
        try:
            with self.connection() as conn:
                if experiment_id:
                    rows = conn.execute(
                        "SELECT * FROM experiment_budget_plans WHERE experiment_id=? ORDER BY updated_at DESC, created_at DESC LIMIT ?",
                        (experiment_id, max(1, int(limit))),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT * FROM experiment_budget_plans ORDER BY updated_at DESC, created_at DESC LIMIT ?",
                        (max(1, int(limit)),),
                    ).fetchall()
            return [plan for plan in (self._budget_plan_from_row(row) for row in rows) if plan is not None]
        except Exception as exc:
            self._record_error(exc)
            return []

    def save_budget_snapshot(self, snapshot: ExperimentBudgetSnapshot) -> dict[str, Any]:
        return self._safe_write(lambda: self._save_budget_snapshot(snapshot), snapshot_id=snapshot.snapshot_id)

    def _save_budget_snapshot(self, snapshot: ExperimentBudgetSnapshot) -> None:
        data = snapshot.to_dict()
        with self.connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO experiment_budget_snapshots
                (snapshot_id, budget_plan_id, experiment_id, total_budget_hint,
                 allocations_json, created_at, raw_payload)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot.snapshot_id,
                    snapshot.budget_plan_id,
                    snapshot.experiment_id,
                    snapshot.total_budget_hint,
                    json_dumps_safe(data.get("allocations_json") or []),
                    snapshot.created_at,
                    json_dumps_safe(data.get("raw_payload") or {}),
                ),
            )
            self._commit(conn)

    def list_budget_snapshots(self, experiment_id: str, limit: int = 20) -> list[ExperimentBudgetSnapshot]:
        try:
            with self.connection() as conn:
                rows = conn.execute(
                    "SELECT * FROM experiment_budget_snapshots WHERE experiment_id=? ORDER BY created_at DESC LIMIT ?",
                    (experiment_id, max(1, int(limit))),
                ).fetchall()
            return [snapshot for snapshot in (self._budget_snapshot_from_row(row) for row in rows) if snapshot is not None]
        except Exception as exc:
            self._record_error(exc)
            return []

    def _compute_summary(self, experiment_id: str, arm_id: str) -> ExperimentSummary:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM experiment_results WHERE experiment_id=? AND arm_id=?",
                (experiment_id, arm_id),
            ).fetchall()
        sample_count = len(rows)
        success_count = sum(1 for row in rows if row["success"] == 1)
        failure_count = sum(1 for row in rows if row["success"] == 0)
        quality_known = [row for row in rows if row["quality_passed"] is not None]
        quality_passed = sum(1 for row in quality_known if row["quality_passed"] == 1)
        return ExperimentSummary(
            experiment_id=experiment_id,
            arm_id=arm_id,
            sample_count=sample_count,
            success_count=success_count,
            failure_count=failure_count,
            avg_reward=_avg(row["reward"] for row in rows),
            avg_sharpe=_avg(row["sharpe"] for row in rows),
            avg_fitness=_avg(row["fitness"] for row in rows),
            avg_platform_sc_abs_max=_avg(row["platform_sc_abs_max"] for row in rows),
            quality_pass_rate=(quality_passed / len(quality_known)) if quality_known else None,
            updated_at=utc_now_iso(),
            raw_payload={"tracking_only": True},
        )

    def _plan_from_row(self, row: Any) -> ExperimentPlan | None:
        if row is None or not hasattr(row, "keys"):
            return None
        data = dict(row)
        return ExperimentPlan.from_dict(
            {
                "experiment_id": data.get("experiment_id"),
                "name": data.get("name"),
                "status": data.get("status"),
                "hypothesis": json_loads_safe(data.get("hypothesis_json"), {}),
                "arms": json_loads_safe(data.get("arms_json"), []),
                "created_at": data.get("created_at"),
                "updated_at": data.get("updated_at"),
                "raw_payload": json_loads_safe(data.get("raw_payload"), {}),
            }
        )

    def _assignment_from_row(self, row: Any) -> ExperimentAssignment | None:
        if row is None or not hasattr(row, "keys"):
            return None
        data = dict(row)
        data["raw_payload"] = json_loads_safe(data.get("raw_payload"), {})
        return ExperimentAssignment.from_dict(data)

    def _result_from_row(self, row: Any) -> ExperimentResult | None:
        if row is None or not hasattr(row, "keys"):
            return None
        data = dict(row)
        data["success"] = _int_to_bool(data.get("success"))
        data["quality_passed"] = _int_to_bool(data.get("quality_passed"))
        data["raw_payload"] = json_loads_safe(data.get("raw_payload"), {})
        return ExperimentResult.from_dict(data)

    def _summary_from_row(self, row: Any) -> ExperimentSummary | None:
        if row is None or not hasattr(row, "keys"):
            return None
        data = dict(row)
        data["raw_payload"] = json_loads_safe(data.get("raw_payload"), {})
        return ExperimentSummary.from_dict(data)

    def _budget_plan_from_row(self, row: Any) -> ExperimentBudgetPlan | None:
        if row is None or not hasattr(row, "keys"):
            return None
        data = dict(row)
        return ExperimentBudgetPlan.from_dict(
            {
                "budget_plan_id": data.get("budget_plan_id"),
                "experiment_id": data.get("experiment_id"),
                "status": data.get("status"),
                "total_budget_hint": data.get("total_budget_hint"),
                "allocations": json_loads_safe(data.get("allocations_json"), []),
                "created_at": data.get("created_at"),
                "updated_at": data.get("updated_at"),
                "generated_by": data.get("generated_by"),
                "raw_payload": json_loads_safe(data.get("raw_payload"), {}),
            }
        )

    def _budget_snapshot_from_row(self, row: Any) -> ExperimentBudgetSnapshot | None:
        if row is None or not hasattr(row, "keys"):
            return None
        data = dict(row)
        return ExperimentBudgetSnapshot.from_dict(
            {
                "snapshot_id": data.get("snapshot_id"),
                "budget_plan_id": data.get("budget_plan_id"),
                "experiment_id": data.get("experiment_id"),
                "total_budget_hint": data.get("total_budget_hint"),
                "allocations_json": json_loads_safe(data.get("allocations_json"), []),
                "created_at": data.get("created_at"),
                "raw_payload": json_loads_safe(data.get("raw_payload"), {}),
            }
        )

    def _safe_write(self, fn: Any, **data: Any) -> dict[str, Any]:
        try:
            fn()
            self.last_error = ""
            return {"ok": True, **data}
        except Exception as exc:
            self._record_error(exc)
            return {"ok": False, "error": str(exc), **data}

    def _record_error(self, exc: Exception) -> None:
        self.last_error = str(exc)
        if self.logger is not None:
            try:
                self.logger.warning("experiment repository operation failed: %s", exc)
            except Exception:
                pass

    def _commit(self, conn: sqlite3.Connection) -> None:
        try:
            conn.commit()
        except Exception:
            pass


def _bool_to_int(value: bool | None) -> int | None:
    if value is None:
        return None
    return 1 if value else 0


def _int_to_bool(value: Any) -> bool | None:
    if value is None or value == "":
        return None
    return bool(int(value))


def _avg(values: Any) -> float | None:
    nums: list[float] = []
    for value in values:
        number = safe_float(value)
        if number is not None:
            nums.append(float(number))
    return (sum(nums) / len(nums)) if nums else None
