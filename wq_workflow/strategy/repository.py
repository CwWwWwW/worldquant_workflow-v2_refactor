from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from wq_workflow.data.json_utils import json_dumps_safe, json_loads_safe
from wq_workflow.data.migrations import initialize_refactor_tables

from .schema import StrategyEvidence, StrategyProfile, StrategyScore, StrategyScoreboard, StrategySignal


class StrategyRepository:
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

    def save_profile(self, profile: StrategyProfile) -> bool:
        data = StrategyProfile.from_dict(profile).to_dict()
        return bool(self._safe(lambda: self._save_profile(data), False))

    def _save_profile(self, data: dict[str, Any]) -> bool:
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO strategy_profiles
                (strategy_id, strategy_type, name, description, source, enabled, advisory_only, created_at, updated_at, raw_payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(strategy_id) DO UPDATE SET
                  strategy_type=excluded.strategy_type,
                  name=excluded.name,
                  description=excluded.description,
                  source=excluded.source,
                  enabled=excluded.enabled,
                  advisory_only=excluded.advisory_only,
                  updated_at=excluded.updated_at,
                  raw_payload=excluded.raw_payload
                """,
                (data["strategy_id"], data["strategy_type"], data["name"], data["description"], data["source"], 1 if data["enabled"] else 0, 1 if data["advisory_only"] else 0, data["created_at"], data["updated_at"], json_dumps_safe(data.get("raw_payload", {}))),
            )
            self._commit(conn)
        return True

    def get_profile(self, strategy_id: str) -> StrategyProfile | None:
        return self._safe(lambda: self._get_profile(strategy_id), None)

    def _get_profile(self, strategy_id: str) -> StrategyProfile | None:
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM strategy_profiles WHERE strategy_id=?", (strategy_id,)).fetchone()
        return _profile_from_row(row)

    def list_profiles(self, strategy_type: str | None = None) -> list[StrategyProfile]:
        return self._safe(lambda: self._list_profiles(strategy_type), []) or []

    def _list_profiles(self, strategy_type: str | None = None) -> list[StrategyProfile]:
        with self.connection() as conn:
            if strategy_type:
                rows = conn.execute("SELECT * FROM strategy_profiles WHERE strategy_type=? ORDER BY strategy_id", (strategy_type,)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM strategy_profiles ORDER BY strategy_id").fetchall()
        return [p for p in (_profile_from_row(row) for row in rows) if p is not None]

    def save_evidence(self, evidence: StrategyEvidence) -> bool:
        data = StrategyEvidence.from_dict(evidence).to_dict()
        return bool(self._safe(lambda: self._save_evidence(data), False))

    def _save_evidence(self, data: dict[str, Any]) -> bool:
        with self.connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO strategy_evidence
                (evidence_id, strategy_id, evidence_type, sample_count, success_count, avg_reward, success_rate,
                 avg_platform_sc_abs_max, quality_pass_rate, replay_confidence, counterfactual_confidence,
                 governance_status, risk_flags_json, reason_codes_json, created_at, raw_payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (data["evidence_id"], data["strategy_id"], data["evidence_type"], data["sample_count"], data.get("success_count"), data.get("avg_reward"), data.get("success_rate"), data.get("avg_platform_sc_abs_max"), data.get("quality_pass_rate"), data.get("replay_confidence"), data.get("counterfactual_confidence"), data.get("governance_status"), json_dumps_safe(data.get("risk_flags", [])), json_dumps_safe(data.get("reason_codes", [])), data["created_at"], json_dumps_safe(data.get("raw_payload", {}))),
            )
            self._commit(conn)
        return True

    def list_evidence(self, strategy_id: str | None = None, evidence_type: str | None = None, limit: int = 1000) -> list[StrategyEvidence]:
        return self._safe(lambda: self._list_evidence(strategy_id, evidence_type, limit), []) or []

    def _list_evidence(self, strategy_id: str | None = None, evidence_type: str | None = None, limit: int = 1000) -> list[StrategyEvidence]:
        clauses = []
        params: list[Any] = []
        if strategy_id:
            clauses.append("strategy_id=?")
            params.append(strategy_id)
        if evidence_type:
            clauses.append("evidence_type=?")
            params.append(evidence_type)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        params.append(max(1, int(limit)))
        with self.connection() as conn:
            rows = conn.execute(f"SELECT * FROM strategy_evidence{where} ORDER BY created_at DESC LIMIT ?", tuple(params)).fetchall()
        return [e for e in (_evidence_from_row(row) for row in rows) if e is not None]

    def save_signal(self, signal: StrategySignal) -> bool:
        data = StrategySignal.from_dict(signal).to_dict()
        return bool(self._safe(lambda: self._save_signal(data), False))

    def _save_signal(self, data: dict[str, Any]) -> bool:
        with self.connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO strategy_signals
                (signal_id, strategy_id, signal_type, value_json, weight, direction, reason, created_at, raw_payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (data["signal_id"], data["strategy_id"], data["signal_type"], json_dumps_safe(data.get("value")), data["weight"], data["direction"], data["reason"], data["created_at"], json_dumps_safe(data.get("raw_payload", {}))),
            )
            self._commit(conn)
        return True

    def list_signals(self, strategy_id: str | None = None, limit: int = 1000) -> list[StrategySignal]:
        return self._safe(lambda: self._list_signals(strategy_id, limit), []) or []

    def _list_signals(self, strategy_id: str | None = None, limit: int = 1000) -> list[StrategySignal]:
        with self.connection() as conn:
            if strategy_id:
                rows = conn.execute("SELECT * FROM strategy_signals WHERE strategy_id=? ORDER BY created_at DESC LIMIT ?", (strategy_id, max(1, int(limit)))).fetchall()
            else:
                rows = conn.execute("SELECT * FROM strategy_signals ORDER BY created_at DESC LIMIT ?", (max(1, int(limit)),)).fetchall()
        return [s for s in (_signal_from_row(row) for row in rows) if s is not None]

    def save_score(self, score: StrategyScore) -> bool:
        data = StrategyScore.from_dict(score).to_dict()
        return bool(self._safe(lambda: self._save_score(data), False))

    def _save_score(self, data: dict[str, Any]) -> bool:
        with self.connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO strategy_scores
                (strategy_id, strategy_type, total_score, reward_score, success_score, sc_risk_score, quality_score,
                 replay_score, counterfactual_score, governance_score, sample_size_score, confidence, risk_level,
                 recommendation, evidence_count, sample_count, updated_at, reason_codes_json, risk_flags_json, raw_payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (data["strategy_id"], data["strategy_type"], data["total_score"], data["reward_score"], data["success_score"], data["sc_risk_score"], data["quality_score"], data["replay_score"], data["counterfactual_score"], data["governance_score"], data["sample_size_score"], data["confidence"], data["risk_level"], data["recommendation"], data["evidence_count"], data["sample_count"], data["updated_at"], json_dumps_safe(data.get("reason_codes", [])), json_dumps_safe(data.get("risk_flags", [])), json_dumps_safe(data.get("raw_payload", {}))),
            )
            self._commit(conn)
        return True

    def get_score(self, strategy_id: str) -> StrategyScore | None:
        return self._safe(lambda: self._get_score(strategy_id), None)

    def _get_score(self, strategy_id: str) -> StrategyScore | None:
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM strategy_scores WHERE strategy_id=?", (strategy_id,)).fetchone()
        return _score_from_row(row)

    def list_scores(self) -> list[StrategyScore]:
        return self._safe(lambda: self._list_scores(), []) or []

    def _list_scores(self) -> list[StrategyScore]:
        with self.connection() as conn:
            rows = conn.execute("SELECT * FROM strategy_scores ORDER BY total_score DESC, strategy_id").fetchall()
        return [s for s in (_score_from_row(row) for row in rows) if s is not None]

    def save_scoreboard(self, scoreboard: StrategyScoreboard) -> bool:
        data = StrategyScoreboard.from_dict(scoreboard).to_dict()
        return bool(self._safe(lambda: self._save_scoreboard(data), False))

    def _save_scoreboard(self, data: dict[str, Any]) -> bool:
        with self.connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO strategy_scoreboards
                (scoreboard_id, generated_at, profiles_json, scores_json, signals_json, evidence_summary_json, warnings_json, raw_payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (data["scoreboard_id"], data["generated_at"], json_dumps_safe(data.get("profiles", [])), json_dumps_safe(data.get("scores", [])), json_dumps_safe(data.get("signals", [])), json_dumps_safe(data.get("evidence_summary", {})), json_dumps_safe(data.get("warnings", [])), json_dumps_safe(data.get("raw_payload", {}))),
            )
            self._commit(conn)
        return True

    def get_latest_scoreboard(self) -> StrategyScoreboard | None:
        return self._safe(lambda: self._get_latest_scoreboard(), None)

    def _get_latest_scoreboard(self) -> StrategyScoreboard | None:
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM strategy_scoreboards ORDER BY generated_at DESC LIMIT 1").fetchone()
        return _scoreboard_from_row(row)

    def list_scoreboards(self, limit: int = 20) -> list[StrategyScoreboard]:
        return self._safe(lambda: self._list_scoreboards(limit), []) or []

    def _list_scoreboards(self, limit: int = 20) -> list[StrategyScoreboard]:
        with self.connection() as conn:
            rows = conn.execute("SELECT * FROM strategy_scoreboards ORDER BY generated_at DESC LIMIT ?", (max(1, int(limit)),)).fetchall()
        return [s for s in (_scoreboard_from_row(row) for row in rows) if s is not None]

    def _safe(self, func: Any, default: Any) -> Any:
        try:
            return func()
        except Exception as exc:
            self.last_error = str(exc)
            try:
                if self.logger is not None:
                    self.logger.warning("strategy repository failure: %s", exc)
            except Exception:
                pass
            return default

    def _commit(self, conn: sqlite3.Connection) -> None:
        try:
            conn.commit()
        except Exception:
            pass


def _profile_from_row(row: Any) -> StrategyProfile | None:
    if row is None or not hasattr(row, "keys"):
        return None
    data = dict(row)
    return StrategyProfile.from_dict({**data, "enabled": bool(data.get("enabled")), "advisory_only": bool(data.get("advisory_only")), "raw_payload": json_loads_safe(data.get("raw_payload"), {})})


def _evidence_from_row(row: Any) -> StrategyEvidence | None:
    if row is None or not hasattr(row, "keys"):
        return None
    data = dict(row)
    data["risk_flags"] = json_loads_safe(data.pop("risk_flags_json", None), [])
    data["reason_codes"] = json_loads_safe(data.pop("reason_codes_json", None), [])
    data["raw_payload"] = json_loads_safe(data.get("raw_payload"), {})
    return StrategyEvidence.from_dict(data)


def _signal_from_row(row: Any) -> StrategySignal | None:
    if row is None or not hasattr(row, "keys"):
        return None
    data = dict(row)
    data["value"] = json_loads_safe(data.pop("value_json", None), None)
    data["raw_payload"] = json_loads_safe(data.get("raw_payload"), {})
    return StrategySignal.from_dict(data)


def _score_from_row(row: Any) -> StrategyScore | None:
    if row is None or not hasattr(row, "keys"):
        return None
    data = dict(row)
    data["reason_codes"] = json_loads_safe(data.pop("reason_codes_json", None), [])
    data["risk_flags"] = json_loads_safe(data.pop("risk_flags_json", None), [])
    data["raw_payload"] = json_loads_safe(data.get("raw_payload"), {})
    return StrategyScore.from_dict(data)


def _scoreboard_from_row(row: Any) -> StrategyScoreboard | None:
    if row is None or not hasattr(row, "keys"):
        return None
    data = dict(row)
    data["profiles"] = json_loads_safe(data.pop("profiles_json", None), [])
    data["scores"] = json_loads_safe(data.pop("scores_json", None), [])
    data["signals"] = json_loads_safe(data.pop("signals_json", None), [])
    data["evidence_summary"] = json_loads_safe(data.pop("evidence_summary_json", None), {})
    data["warnings"] = json_loads_safe(data.pop("warnings_json", None), [])
    data["raw_payload"] = json_loads_safe(data.get("raw_payload"), {})
    return StrategyScoreboard.from_dict(data)
