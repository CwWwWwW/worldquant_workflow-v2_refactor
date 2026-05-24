from __future__ import annotations

import json
import math
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .events import json_dumps_safe

ACTIONS = {"keep_active", "keep_shadow", "reduce_weight", "retrain", "rollback", "disable_model", "force_legacy"}

DDL = """
CREATE TABLE IF NOT EXISTS ml_online_evaluation (
    eval_id TEXT PRIMARY KEY,
    task_name TEXT,
    model_version TEXT,
    window_start TEXT,
    window_end TEXT,
    sample_count INTEGER,
    prediction_count INTEGER,
    success_count INTEGER,
    failure_count INTEGER,
    mae REAL,
    rmse REAL,
    precision_score REAL,
    recall_score REAL,
    hit_rate REAL,
    avg_reward_delta REAL,
    avg_sc_error REAL,
    drift_score REAL,
    degradation_score REAL,
    recommended_action TEXT,
    raw_payload TEXT,
    created_at TEXT
);
"""


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _loads(value: Any, default: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return default
    return value if value is not None else default


def _float(value: Any) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except Exception:
        return None


@dataclass
class OnlineEvaluationResult:
    eval_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    task_name: str = ""
    model_version: str = ""
    window_start: str = ""
    window_end: str = field(default_factory=utc_now_iso)
    sample_count: int = 0
    prediction_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    mae: float | None = None
    rmse: float | None = None
    precision_score: float | None = None
    recall_score: float | None = None
    hit_rate: float | None = None
    avg_reward_delta: float | None = None
    avg_sc_error: float | None = None
    drift_score: float | None = None
    degradation_score: float | None = None
    recommended_action: str = "keep_shadow"
    raw_payload: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "OnlineEvaluationResult":
        data = dict(data) if isinstance(data, dict) else {}
        allowed = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: data.get(k) for k in allowed if k in data})


class OnlineEvaluator:
    def __init__(self, conn: sqlite3.Connection | None = None, db_path: str | Path | None = None, config: Any | None = None, logger: Any | None = None, repository: Any | None = None) -> None:
        self.conn = conn
        self.db_path = Path(db_path) if db_path is not None else None
        self.config = config
        self.logger = logger
        self.repository = repository

    def _warn(self, message: str, *args: Any) -> None:
        try:
            if self.logger is not None:
                self.logger.warning(message, *args)
        except Exception:
            pass

    def _connect(self) -> sqlite3.Connection | None:
        if self.conn is not None:
            return self.conn
        if self.db_path is None:
            return None
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _fetch(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        conn = None
        close = False
        try:
            conn = self._connect()
            if conn is None:
                return []
            close = self.conn is None
            conn.row_factory = sqlite3.Row
            return [dict(r) for r in conn.execute(sql, params).fetchall()]
        except Exception as exc:
            self._warn("online eval query failed: %s", exc)
            return []
        finally:
            if close and conn is not None:
                conn.close()

    def evaluate_task(self, task_name: str, model_version: str | None = None) -> OnlineEvaluationResult:
        try:
            task = str(task_name or "")
            if task == "sc":
                result = self._evaluate_sc(str(model_version or ""))
            elif task in {"parent", "policy"}:
                result = self._evaluate_decision_task(task, str(model_version or ""))
            elif task in {"simulator", "outcome"}:
                result = self._evaluate_simulator(str(model_version or ""))
            elif task == "insight":
                result = self._evaluate_insight(str(model_version or ""))
            else:
                result = OnlineEvaluationResult(task_name=task, model_version=str(model_version or ""), recommended_action="keep_shadow", raw_payload={"reason": "unknown_task"})
            self.persist(result)
            return result
        except Exception as exc:
            self._warn("online evaluation failed for %s: %s", task_name, exc)
            result = OnlineEvaluationResult(task_name=str(task_name or ""), model_version=str(model_version or ""), recommended_action="keep_shadow", raw_payload={"error": str(exc)})
            self.persist(result)
            return result

    def _evaluate_sc(self, model_version: str) -> OnlineEvaluationResult:
        rows = self._fetch("SELECT * FROM ml_prediction_audit WHERE task_name = ? ORDER BY created_at DESC LIMIT 500", ("sc",))
        errors: list[float] = []
        details: list[dict[str, Any]] = []
        for row in rows:
            pred = _loads(row.get("prediction_json"), {})
            raw = _loads(row.get("raw_payload"), {})
            learned = _float(pred.get("learned_local_sc") if isinstance(pred, dict) else None)
            actual = None
            if isinstance(raw, dict):
                actual = _float(raw.get("platform_sc_abs_max") or raw.get("actual_platform_sc_abs_max"))
                platform_sc = raw.get("platform_sc") if isinstance(raw.get("platform_sc"), dict) else {}
                actual = actual if actual is not None else _float(platform_sc.get("abs_max"))
            if learned is None or actual is None:
                continue
            err = abs(abs(learned) - abs(actual))
            errors.append(err)
            details.append({"prediction_id": row.get("prediction_id"), "learned": learned, "actual": actual, "error": err})
        sample_count = len(errors)
        mae = sum(errors) / sample_count if sample_count else None
        rmse = math.sqrt(sum(e * e for e in errors) / sample_count) if sample_count else None
        min_samples = int(getattr(self.config, "sc_online_eval_min_samples", 30) or 30)
        max_mae = float(getattr(self.config, "sc_model_max_mae", 0.15) or 0.15)
        action = "keep_shadow"
        if sample_count >= min_samples:
            action = "keep_active" if (mae is not None and mae <= max_mae) else "reduce_weight"
            if mae is not None and mae > max_mae * 1.5:
                action = "disable_model"
        return OnlineEvaluationResult(task_name="sc", model_version=model_version, sample_count=sample_count, prediction_count=len(rows), mae=mae, rmse=rmse, avg_sc_error=mae, recommended_action=action, raw_payload={"matched_samples": details[:50], "min_samples": min_samples, "max_mae": max_mae})

    def _evaluate_decision_task(self, task: str, model_version: str) -> OnlineEvaluationResult:
        decision_type = "parent_selection" if task == "parent" else "policy_action"
        rows = self._fetch(
            """
            SELECT d.*, o.reward_delta, o.success, o.failure_type, o.platform_sc_abs_max
            FROM decision_snapshots d LEFT JOIN decision_outcomes o ON d.decision_id = o.decision_id
            WHERE d.decision_type = ? ORDER BY d.created_at DESC LIMIT 500
            """,
            (decision_type,),
        )
        deltas = [_float(r.get("reward_delta")) for r in rows]
        deltas = [d for d in deltas if d is not None]
        sample_count = len(deltas)
        min_samples = int(getattr(self.config, f"{task}_online_eval_min_samples", 30) or 30)
        avg_delta = sum(deltas) / sample_count if sample_count else None
        success = sum(1 for r in rows if int(r.get("success") or 0) == 1)
        failure = sum(1 for r in rows if r.get("success") is not None and int(r.get("success") or 0) == 0)
        action = "keep_shadow"
        if sample_count >= min_samples:
            action = "keep_active" if (avg_delta is not None and avg_delta >= 0.0) else "reduce_weight"
            if avg_delta is not None and avg_delta < -0.05:
                action = "disable_model"
        return OnlineEvaluationResult(task_name=task, model_version=model_version, sample_count=sample_count, prediction_count=len(rows), success_count=success, failure_count=failure, avg_reward_delta=avg_delta, recommended_action=action, raw_payload={"min_samples": min_samples, "decision_type": decision_type})

    def _evaluate_simulator(self, model_version: str) -> OnlineEvaluationResult:
        rows = self._fetch("SELECT * FROM simulator_training_samples ORDER BY created_at DESC LIMIT 500")
        min_samples = int(getattr(self.config, "simulator_online_eval_min_samples", 50) or 50)
        false_flags = []
        for row in rows:
            raw = _loads(row.get("raw_payload"), {})
            if isinstance(raw, dict) and "skip_would_have_been_wrong" in raw:
                false_flags.append(bool(raw.get("skip_would_have_been_wrong")))
        sample_count = len(false_flags)
        action = "force_legacy" if sample_count == 0 else "keep_shadow"
        false_rate = (sum(1 for x in false_flags if x) / sample_count) if sample_count else None
        max_rate = float(getattr(self.config, "simulator_max_false_skip_rate", 0.02) or 0.02)
        if sample_count >= min_samples:
            action = "keep_shadow" if (false_rate is not None and false_rate <= max_rate) else "disable_model"
        return OnlineEvaluationResult(task_name="simulator", model_version=model_version, sample_count=sample_count, prediction_count=len(rows), hit_rate=(1.0 - false_rate) if false_rate is not None else None, recommended_action=action, raw_payload={"false_skip_rate": false_rate, "max_false_skip_rate": max_rate, "min_samples": min_samples})

    def _evaluate_insight(self, model_version: str) -> OnlineEvaluationResult:
        rows = self._fetch("SELECT * FROM insight_effect_samples ORDER BY created_at DESC LIMIT 500")
        rewards = [_float(r.get("reward")) for r in rows]
        rewards = [r for r in rewards if r is not None]
        sample_count = len(rewards)
        avg = sum(rewards) / sample_count if sample_count else None
        action = "keep_shadow" if sample_count < int(getattr(self.config, "insight_min_samples", 20) or 20) else ("disable_model" if avg is not None and avg < 0 else "keep_active")
        return OnlineEvaluationResult(task_name="insight", model_version=model_version, sample_count=sample_count, avg_reward_delta=avg, recommended_action=action, raw_payload={"advisory_only": True})

    def persist(self, result: OnlineEvaluationResult) -> bool:
        conn = None
        close = False
        try:
            conn = self._connect()
            if conn is None:
                return False
            close = self.conn is None
            conn.execute(DDL)
            conn.execute(
                """
                INSERT OR REPLACE INTO ml_online_evaluation
                (eval_id, task_name, model_version, window_start, window_end, sample_count, prediction_count, success_count, failure_count, mae, rmse, precision_score, recall_score, hit_rate, avg_reward_delta, avg_sc_error, drift_score, degradation_score, recommended_action, raw_payload, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (result.eval_id, result.task_name, result.model_version, result.window_start, result.window_end, result.sample_count, result.prediction_count, result.success_count, result.failure_count, result.mae, result.rmse, result.precision_score, result.recall_score, result.hit_rate, result.avg_reward_delta, result.avg_sc_error, result.drift_score, result.degradation_score, result.recommended_action, json_dumps_safe(result.raw_payload), result.created_at),
            )
            conn.commit()
            return True
        except Exception as exc:
            self._warn("online evaluation persist failed: %s", exc)
            return False
        finally:
            if close and conn is not None:
                conn.close()
