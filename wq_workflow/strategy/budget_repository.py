from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from wq_workflow.data.json_utils import json_dumps_safe, json_loads_safe
from wq_workflow.data.migrations import initialize_refactor_tables

from .budget_schema import StrategyBudgetAllocation, StrategyBudgetPlan, StrategyBudgetReport, StrategyBudgetRule


class StrategyBudgetRepository:
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
            raise RuntimeError("database path unavailable")
        from wq_workflow.storage.schema import initialize_schema
        from wq_workflow.storage.sqlite_store import connect_db

        conn = connect_db(self.db_path)
        try:
            initialize_schema(conn)
            initialize_refactor_tables(conn)
            yield conn
        finally:
            conn.close()

    def initialize(self) -> dict[str, Any]:
        return self._safe(lambda: self._initialize(), {"ok": False})

    def _initialize(self) -> dict[str, Any]:
        with self.connection() as conn:
            initialize_refactor_tables(conn)
            self._commit(conn)
        return {"ok": True}

    def save_rule(self, rule: StrategyBudgetRule) -> bool:
        data = StrategyBudgetRule.from_dict(rule).to_dict()
        return bool(self._safe(lambda: self._save_rule(data), False))

    def _save_rule(self, data: dict[str, Any]) -> bool:
        with self.connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO strategy_budget_rules
                (rule_id, rule_type, description, enabled, priority, min_ratio, max_ratio, applies_to_state,
                 applies_to_strategy_type, reason_code, created_at, raw_payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (data["rule_id"], data["rule_type"], data["description"], 1 if data.get("enabled") else 0, data["priority"], data.get("min_ratio"), data.get("max_ratio"), data.get("applies_to_state"), data.get("applies_to_strategy_type"), data["reason_code"], data["created_at"], json_dumps_safe(data.get("raw_payload", {}))),
            )
            self._commit(conn)
        return True

    def list_rules(self, rule_type: str | None = None) -> list[StrategyBudgetRule]:
        return self._safe(lambda: self._list_rules(rule_type), []) or []

    def _list_rules(self, rule_type: str | None = None) -> list[StrategyBudgetRule]:
        with self.connection() as conn:
            if rule_type:
                rows = conn.execute("SELECT * FROM strategy_budget_rules WHERE rule_type=? ORDER BY priority, rule_id", (rule_type,)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM strategy_budget_rules ORDER BY priority, rule_id").fetchall()
        return [item for item in (_rule_from_row(row) for row in rows) if item is not None]

    def save_allocation(self, allocation: StrategyBudgetAllocation) -> bool:
        data = StrategyBudgetAllocation.from_dict(allocation).to_dict()
        return bool(self._safe(lambda: self._save_allocation(data), False))

    def _save_allocation(self, data: dict[str, Any]) -> bool:
        with self.connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO strategy_budget_allocations
                (allocation_id, plan_id, strategy_id, strategy_type, state, role, score, confidence, risk_level,
                 requested_ratio, suggested_ratio, min_floor_ratio, hard_cap_ratio, suggested_slots, budget_status,
                 reason_codes_json, risk_flags_json, auto_apply_allowed, created_at, raw_payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (data["allocation_id"], data["plan_id"], data["strategy_id"], data["strategy_type"], data["state"], data["role"], data["score"], data["confidence"], data["risk_level"], data["requested_ratio"], data["suggested_ratio"], data["min_floor_ratio"], data["hard_cap_ratio"], data.get("suggested_slots"), data["budget_status"], json_dumps_safe(data.get("reason_codes", [])), json_dumps_safe(data.get("risk_flags", [])), 0, data["created_at"], json_dumps_safe(data.get("raw_payload", {}))),
            )
            self._commit(conn)
        return True

    def list_allocations(self, plan_id: str | None = None, strategy_id: str | None = None, limit: int = 1000) -> list[StrategyBudgetAllocation]:
        return self._safe(lambda: self._list_allocations(plan_id, strategy_id, limit), []) or []

    def _list_allocations(self, plan_id: str | None = None, strategy_id: str | None = None, limit: int = 1000) -> list[StrategyBudgetAllocation]:
        clauses: list[str] = []
        params: list[Any] = []
        if plan_id:
            clauses.append("plan_id=?")
            params.append(plan_id)
        if strategy_id:
            clauses.append("strategy_id=?")
            params.append(strategy_id)
        sql = "SELECT * FROM strategy_budget_allocations"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(max(1, int(limit)))
        with self.connection() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        return [item for item in (_allocation_from_row(row) for row in rows) if item is not None]

    def save_plan(self, plan: StrategyBudgetPlan) -> bool:
        data = StrategyBudgetPlan.from_dict(plan).to_dict()
        return bool(self._safe(lambda: self._save_plan(data), False))

    def _save_plan(self, data: dict[str, Any]) -> bool:
        with self.connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO strategy_budget_plans
                (plan_id, generated_at, mode, total_budget_hint, allocations_json, total_suggested_ratio, warnings_json, raw_payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (data["plan_id"], data["generated_at"], data["mode"], data.get("total_budget_hint"), json_dumps_safe(data.get("allocations", [])), data.get("total_suggested_ratio"), json_dumps_safe(data.get("warnings", [])), json_dumps_safe(data.get("raw_payload", {}))),
            )
            self._commit(conn)
        return True

    def get_latest_plan(self) -> StrategyBudgetPlan | None:
        return self._safe(lambda: self._get_latest_plan(), None)

    def _get_latest_plan(self) -> StrategyBudgetPlan | None:
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM strategy_budget_plans ORDER BY generated_at DESC LIMIT 1").fetchone()
        return _plan_from_row(row)

    def list_plans(self, limit: int = 20) -> list[StrategyBudgetPlan]:
        return self._safe(lambda: self._list_plans(limit), []) or []

    def _list_plans(self, limit: int = 20) -> list[StrategyBudgetPlan]:
        with self.connection() as conn:
            rows = conn.execute("SELECT * FROM strategy_budget_plans ORDER BY generated_at DESC LIMIT ?", (max(1, int(limit)),)).fetchall()
        return [item for item in (_plan_from_row(row) for row in rows) if item is not None]

    def save_report(self, report: StrategyBudgetReport) -> bool:
        data = StrategyBudgetReport.from_dict(report).to_dict()
        return bool(self._safe(lambda: self._save_report(data), False))

    def _save_report(self, data: dict[str, Any]) -> bool:
        with self.connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO strategy_budget_reports
                (report_id, generated_at, mode, total_budget_hint, allocations_json, warnings_json, raw_payload)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (data["report_id"], data["generated_at"], data["mode"], data.get("total_budget_hint"), json_dumps_safe(data.get("allocations", [])), json_dumps_safe(data.get("warnings", [])), json_dumps_safe(data.get("raw_payload", {}))),
            )
            self._commit(conn)
        return True

    def get_latest_report(self) -> StrategyBudgetReport | None:
        return self._safe(lambda: self._get_latest_report(), None)

    def _get_latest_report(self) -> StrategyBudgetReport | None:
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM strategy_budget_reports ORDER BY generated_at DESC LIMIT 1").fetchone()
        return _report_from_row(row)

    def _safe(self, func: Any, default: Any) -> Any:
        try:
            return func()
        except Exception as exc:
            self.last_error = str(exc)
            try:
                if self.logger is not None:
                    self.logger.warning("strategy budget repository failure: %s", exc)
            except Exception:
                pass
            return default

    def _commit(self, conn: sqlite3.Connection) -> None:
        try:
            conn.commit()
        except Exception:
            pass


def _rule_from_row(row: Any) -> StrategyBudgetRule | None:
    if row is None or not hasattr(row, "keys"):
        return None
    data = dict(row)
    data["enabled"] = bool(data.get("enabled"))
    data["raw_payload"] = json_loads_safe(data.get("raw_payload"), {})
    return StrategyBudgetRule.from_dict(data)


def _allocation_from_row(row: Any) -> StrategyBudgetAllocation | None:
    if row is None or not hasattr(row, "keys"):
        return None
    data = dict(row)
    data["reason_codes"] = json_loads_safe(data.pop("reason_codes_json", None), [])
    data["risk_flags"] = json_loads_safe(data.pop("risk_flags_json", None), [])
    data["auto_apply_allowed"] = False
    data["raw_payload"] = json_loads_safe(data.get("raw_payload"), {})
    return StrategyBudgetAllocation.from_dict(data)


def _plan_from_row(row: Any) -> StrategyBudgetPlan | None:
    if row is None or not hasattr(row, "keys"):
        return None
    data = dict(row)
    data["allocations"] = json_loads_safe(data.pop("allocations_json", None), [])
    data["warnings"] = json_loads_safe(data.pop("warnings_json", None), [])
    data["raw_payload"] = json_loads_safe(data.get("raw_payload"), {})
    return StrategyBudgetPlan.from_dict(data)


def _report_from_row(row: Any) -> StrategyBudgetReport | None:
    if row is None or not hasattr(row, "keys"):
        return None
    data = dict(row)
    data["allocations"] = json_loads_safe(data.pop("allocations_json", None), [])
    data["warnings"] = json_loads_safe(data.pop("warnings_json", None), [])
    data["raw_payload"] = json_loads_safe(data.get("raw_payload"), {})
    return StrategyBudgetReport.from_dict(data)
