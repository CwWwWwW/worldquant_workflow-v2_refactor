from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from wq_workflow.data.json_utils import json_dumps_safe, json_loads_safe
from wq_workflow.data.migrations import initialize_refactor_tables

from .portfolio_schema import StrategyPortfolio, StrategyPortfolioReport, StrategyState, StrategyTransition


class StrategyPortfolioRepository:
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

    def save_state(self, state: StrategyState) -> bool:
        data = StrategyState.from_dict(state).to_dict()
        return bool(self._safe(lambda: self._save_state(data), False))

    def _save_state(self, data: dict[str, Any]) -> bool:
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO strategy_portfolio_states
                (strategy_id, strategy_type, current_state, recommended_state, current_role, confidence, risk_level,
                 score, sample_count, evidence_count, governance_status, reason_codes_json, risk_flags_json, updated_at, raw_payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(strategy_id) DO UPDATE SET
                  strategy_type=excluded.strategy_type,
                  current_state=excluded.current_state,
                  recommended_state=excluded.recommended_state,
                  current_role=excluded.current_role,
                  confidence=excluded.confidence,
                  risk_level=excluded.risk_level,
                  score=excluded.score,
                  sample_count=excluded.sample_count,
                  evidence_count=excluded.evidence_count,
                  governance_status=excluded.governance_status,
                  reason_codes_json=excluded.reason_codes_json,
                  risk_flags_json=excluded.risk_flags_json,
                  updated_at=excluded.updated_at,
                  raw_payload=excluded.raw_payload
                """,
                (data["strategy_id"], data["strategy_type"], data["current_state"], data["recommended_state"], data["current_role"], data["confidence"], data["risk_level"], data["score"], data["sample_count"], data["evidence_count"], data.get("governance_status"), json_dumps_safe(data.get("reason_codes", [])), json_dumps_safe(data.get("risk_flags", [])), data["updated_at"], json_dumps_safe(data.get("raw_payload", {}))),
            )
            self._commit(conn)
        return True

    def get_state(self, strategy_id: str) -> StrategyState | None:
        return self._safe(lambda: self._get_state(strategy_id), None)

    def _get_state(self, strategy_id: str) -> StrategyState | None:
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM strategy_portfolio_states WHERE strategy_id=?", (strategy_id,)).fetchone()
        return _state_from_row(row)

    def list_states(self) -> list[StrategyState]:
        return self._safe(lambda: self._list_states(), []) or []

    def _list_states(self) -> list[StrategyState]:
        with self.connection() as conn:
            rows = conn.execute("SELECT * FROM strategy_portfolio_states ORDER BY current_role, strategy_id").fetchall()
        return [item for item in (_state_from_row(row) for row in rows) if item is not None]

    def save_transition(self, transition: StrategyTransition) -> bool:
        data = StrategyTransition.from_dict(transition).to_dict()
        return bool(self._safe(lambda: self._save_transition(data), False))

    def _save_transition(self, data: dict[str, Any]) -> bool:
        with self.connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO strategy_portfolio_transitions
                (transition_id, strategy_id, from_state, to_state, recommendation, allowed, auto_apply_allowed,
                 confidence, reason_codes_json, risk_flags_json, created_at, raw_payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (data["transition_id"], data["strategy_id"], data["from_state"], data["to_state"], data["recommendation"], 1 if data.get("allowed") else 0, 0, data["confidence"], json_dumps_safe(data.get("reason_codes", [])), json_dumps_safe(data.get("risk_flags", [])), data["created_at"], json_dumps_safe(data.get("raw_payload", {}))),
            )
            self._commit(conn)
        return True

    def list_transitions(self, strategy_id: str | None = None, limit: int = 1000) -> list[StrategyTransition]:
        return self._safe(lambda: self._list_transitions(strategy_id, limit), []) or []

    def _list_transitions(self, strategy_id: str | None = None, limit: int = 1000) -> list[StrategyTransition]:
        with self.connection() as conn:
            if strategy_id:
                rows = conn.execute("SELECT * FROM strategy_portfolio_transitions WHERE strategy_id=? ORDER BY created_at DESC LIMIT ?", (strategy_id, max(1, int(limit)))).fetchall()
            else:
                rows = conn.execute("SELECT * FROM strategy_portfolio_transitions ORDER BY created_at DESC LIMIT ?", (max(1, int(limit)),)).fetchall()
        return [item for item in (_transition_from_row(row) for row in rows) if item is not None]

    def save_portfolio(self, portfolio: StrategyPortfolio) -> bool:
        data = StrategyPortfolio.from_dict(portfolio).to_dict()
        return bool(self._safe(lambda: self._save_portfolio(data), False))

    def _save_portfolio(self, data: dict[str, Any]) -> bool:
        with self.connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO strategy_portfolios
                (portfolio_id, generated_at, champion_strategy_id, states_json, transitions_json, warnings_json, raw_payload)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (data["portfolio_id"], data["generated_at"], data["champion_strategy_id"], json_dumps_safe(data.get("states", [])), json_dumps_safe(data.get("transitions", [])), json_dumps_safe(data.get("warnings", [])), json_dumps_safe(data.get("raw_payload", {}))),
            )
            self._commit(conn)
        return True

    def get_latest_portfolio(self) -> StrategyPortfolio | None:
        return self._safe(lambda: self._get_latest_portfolio(), None)

    def _get_latest_portfolio(self) -> StrategyPortfolio | None:
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM strategy_portfolios ORDER BY generated_at DESC LIMIT 1").fetchone()
        return _portfolio_from_row(row)

    def list_portfolios(self, limit: int = 20) -> list[StrategyPortfolio]:
        return self._safe(lambda: self._list_portfolios(limit), []) or []

    def _list_portfolios(self, limit: int = 20) -> list[StrategyPortfolio]:
        with self.connection() as conn:
            rows = conn.execute("SELECT * FROM strategy_portfolios ORDER BY generated_at DESC LIMIT ?", (max(1, int(limit)),)).fetchall()
        return [item for item in (_portfolio_from_row(row) for row in rows) if item is not None]

    def save_report(self, report: StrategyPortfolioReport) -> bool:
        data = StrategyPortfolioReport.from_dict(report).to_dict()
        return bool(self._safe(lambda: self._save_report(data), False))

    def _save_report(self, data: dict[str, Any]) -> bool:
        with self.connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO strategy_portfolio_reports
                (report_id, generated_at, mode, champion_strategy_id, strategy_states_json,
                 recommended_transitions_json, warnings_json, raw_payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (data["report_id"], data["generated_at"], data["mode"], data["champion_strategy_id"], json_dumps_safe(data.get("strategy_states", [])), json_dumps_safe(data.get("recommended_transitions", [])), json_dumps_safe(data.get("warnings", [])), json_dumps_safe(data.get("raw_payload", {}))),
            )
            self._commit(conn)
        return True

    def get_latest_report(self) -> StrategyPortfolioReport | None:
        return self._safe(lambda: self._get_latest_report(), None)

    def _get_latest_report(self) -> StrategyPortfolioReport | None:
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM strategy_portfolio_reports ORDER BY generated_at DESC LIMIT 1").fetchone()
        return _report_from_row(row)

    def _safe(self, func: Any, default: Any) -> Any:
        try:
            return func()
        except Exception as exc:
            self.last_error = str(exc)
            try:
                if self.logger is not None:
                    self.logger.warning("strategy portfolio repository failure: %s", exc)
            except Exception:
                pass
            return default

    def _commit(self, conn: sqlite3.Connection) -> None:
        try:
            conn.commit()
        except Exception:
            pass


def _state_from_row(row: Any) -> StrategyState | None:
    if row is None or not hasattr(row, "keys"):
        return None
    data = dict(row)
    data["reason_codes"] = json_loads_safe(data.pop("reason_codes_json", None), [])
    data["risk_flags"] = json_loads_safe(data.pop("risk_flags_json", None), [])
    data["raw_payload"] = json_loads_safe(data.get("raw_payload"), {})
    return StrategyState.from_dict(data)


def _transition_from_row(row: Any) -> StrategyTransition | None:
    if row is None or not hasattr(row, "keys"):
        return None
    data = dict(row)
    data["allowed"] = bool(data.get("allowed"))
    data["auto_apply_allowed"] = False
    data["reason_codes"] = json_loads_safe(data.pop("reason_codes_json", None), [])
    data["risk_flags"] = json_loads_safe(data.pop("risk_flags_json", None), [])
    data["raw_payload"] = json_loads_safe(data.get("raw_payload"), {})
    return StrategyTransition.from_dict(data)


def _portfolio_from_row(row: Any) -> StrategyPortfolio | None:
    if row is None or not hasattr(row, "keys"):
        return None
    data = dict(row)
    data["states"] = json_loads_safe(data.pop("states_json", None), [])
    data["transitions"] = json_loads_safe(data.pop("transitions_json", None), [])
    data["warnings"] = json_loads_safe(data.pop("warnings_json", None), [])
    data["raw_payload"] = json_loads_safe(data.get("raw_payload"), {})
    return StrategyPortfolio.from_dict(data)


def _report_from_row(row: Any) -> StrategyPortfolioReport | None:
    if row is None or not hasattr(row, "keys"):
        return None
    data = dict(row)
    data["strategy_states"] = json_loads_safe(data.pop("strategy_states_json", None), [])
    data["recommended_transitions"] = json_loads_safe(data.pop("recommended_transitions_json", None), [])
    data["warnings"] = json_loads_safe(data.pop("warnings_json", None), [])
    data["raw_payload"] = json_loads_safe(data.get("raw_payload"), {})
    return StrategyPortfolioReport.from_dict(data)
