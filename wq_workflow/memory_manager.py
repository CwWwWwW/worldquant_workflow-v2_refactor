from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from .core.operator_graph import OperatorGraph
from .core.parser import ExpressionParser, ParseError
from .paths import (
    ALPHA_LINEAGE_FILE,
    FAILURE_PATTERNS_FILE,
    OPERATOR_STATISTICS_FILE,
)
from .platform_sc import sc_payload_from_metrics
from .safe_io import atomic_write_json, finite_float, safe_read_json
from memory.file_locks import lock_for_memory_path


MAX_LINEAGE_ROWS = 2_000
MAX_FAILURE_ROWS = 1_000


class EvolutionMemory:
    def __init__(
        self,
        lineage_file: Path = ALPHA_LINEAGE_FILE,
        failures_file: Path = FAILURE_PATTERNS_FILE,
        statistics_file: Path = OPERATOR_STATISTICS_FILE,
    ) -> None:
        self.lineage_file = lineage_file
        self.failures_file = failures_file
        self.statistics_file = statistics_file
        self._ensure_files()

    def save_mutation(
        self,
        *,
        alpha_id: str,
        parent_id: str,
        expression_before: str,
        expression_after: str,
        mutation_type: str,
        metrics_before: dict[str, float] | None,
        metrics_after: dict[str, float] | None,
        delta: dict[str, float] | None,
        passed: bool,
        reward: float = 0.0,
        quality_passed: bool = False,
        failure_reason: str = "",
        complexity_before: dict[str, int] | None = None,
        complexity_after: dict[str, int] | None = None,
        timestamp: str | None = None,
        behavior_family: str = "",
        behavior_fingerprint: dict[str, Any] | None = None,
        estimated_self_corr: float | None = None,
        family_reward_inheritance: dict[str, Any] | None = None,
        lineage_depth: int = 0,
    ) -> dict[str, Any]:
        with lock_for_memory_path(self.lineage_file):
            record = {
                "alpha_id": alpha_id,
                "parent_id": parent_id,
                "expression_before": expression_before,
                "expression_after": expression_after,
                "mutation_type": mutation_type,
                "metrics_before": metrics_before or {"sharpe": 0, "fitness": 0, "turnover": 0},
                "metrics_after": metrics_after or {"sharpe": 0, "fitness": 0, "turnover": 0},
                "delta": delta or {"sharpe": 0, "fitness": 0, "turnover": 0},
                "passed": bool(passed),
                "timestamp": timestamp or _now(),
                "reward": finite_float(reward),
                "quality_passed": bool(quality_passed),
                "failure_reason": failure_reason,
                "complexity_before": complexity_before or {},
                "complexity_after": complexity_after or {},
            }
            if behavior_family:
                record["behavior_family"] = behavior_family
            if behavior_fingerprint is not None:
                record["behavior_fingerprint"] = behavior_fingerprint
            if estimated_self_corr is not None:
                record["estimated_self_corr"] = finite_float(estimated_self_corr)
            if family_reward_inheritance is not None:
                record["family_reward_inheritance"] = family_reward_inheritance
            if lineage_depth:
                record["lineage_depth"] = max(0, int(lineage_depth))
            record.update(sc_payload_from_metrics(record.get("metrics_after") if isinstance(record.get("metrics_after"), dict) else {}))
            rows = self._read_list(self.lineage_file)
            rows.append(record)
            rows = rows[-MAX_LINEAGE_ROWS:]
            self._write_json(self.lineage_file, rows)
            self._refresh_operator_statistics(rows)
            try:
                from .storage import get_storage_manager

                get_storage_manager().write_lineage_record(record)
            except Exception:
                pass
            return record

    def load_recent_history(self, limit: int = 20) -> list[dict[str, Any]]:
        rows = self._read_list(self.lineage_file)
        return rows[-limit:]

    def get_best_mutations(self, limit: int = 5) -> list[dict[str, Any]]:
        rows = self._read_list(self.lineage_file)
        successful = [row for row in rows if _float(row.get("reward")) > 0 or row.get("passed")]
        successful.sort(key=lambda row: (_float(row.get("reward")), _float(row.get("delta", {}).get("sharpe"))), reverse=True)
        return successful[:limit]

    def get_failure_patterns(self, limit: int = 5, error_type: str = "") -> list[dict[str, Any]]:
        rows = self._read_list(self.failures_file)
        if error_type:
            rows = [row for row in rows if str(row.get("error_type", "")).lower() == error_type.lower()]
        return rows[-limit:]

    def get_operator_statistics(self) -> dict[str, dict[str, float]]:
        self._refresh_operator_statistics(self._read_list(self.lineage_file))
        data = self._read_json(self.statistics_file, {})
        return data if isinstance(data, dict) else {}

    def save_failure_pattern(
        self,
        *,
        error_type: str,
        expression: str,
        root_cause: str,
        successful_fix: str = "",
        timestamp: str | None = None,
    ) -> dict[str, Any]:
        with lock_for_memory_path(self.failures_file):
            record = {
                "error_type": error_type,
                "expression": expression,
                "root_cause": root_cause,
                "successful_fix": successful_fix,
                "timestamp": timestamp or _now(),
            }
            rows = self._read_list(self.failures_file)
            rows.append(record)
            rows = rows[-MAX_FAILURE_ROWS:]
            self._write_json(self.failures_file, rows)
            try:
                from .storage import get_storage_manager

                get_storage_manager().write_failure_record(record)
            except Exception:
                pass
            return record

    def record_successful_fix(self, *, error_type: str = "", expression: str = "", successful_fix: str) -> bool:
        with lock_for_memory_path(self.failures_file):
            rows = self._read_list(self.failures_file)
            for row in reversed(rows):
                if row.get("successful_fix"):
                    continue
                if error_type and str(row.get("error_type", "")).lower() != error_type.lower():
                    continue
                if expression and str(row.get("expression", "")) != expression:
                    continue
                row["successful_fix"] = successful_fix
                self._write_json(self.failures_file, rows)
                try:
                    from .storage import get_storage_manager

                    get_storage_manager().mirror_json_snapshot(self.failures_file, rows)
                except Exception:
                    pass
                return True
            return False

    def _refresh_operator_statistics(self, rows: list[dict[str, Any]]) -> None:
        grouped: dict[str, dict[str, float]] = {}
        operator_graph = OperatorGraph()
        parser = ExpressionParser()
        for row in rows:
            mutation = str(row.get("mutation_type") or "unknown")
            delta = row.get("delta") if isinstance(row.get("delta"), dict) else {}
            bucket = grouped.setdefault(
                mutation,
                {
                    "count": 0.0,
                    "success_count": 0.0,
                    "sharpe_gain": 0.0,
                    "fitness_gain": 0.0,
                    "turnover_reduction": 0.0,
                },
            )
            bucket["count"] += 1
            reward = _float(row.get("reward"))
            if reward > 0 or row.get("passed"):
                bucket["success_count"] += 1
            bucket["sharpe_gain"] += _float(delta.get("sharpe"))
            bucket["fitness_gain"] += _float(delta.get("fitness"))
            bucket["turnover_reduction"] += -_float(delta.get("turnover"))
            expression = str(row.get("expression_after") or "")
            if expression:
                try:
                    ast = parser.parse(expression)
                except ParseError:
                    ast = None
                if ast is not None:
                    operator_graph.record(ast, reward=reward, success=bool(reward > 0 or row.get("passed")))

        stats: dict[str, dict[str, float]] = {}
        for mutation, values in grouped.items():
            count = max(values["count"], 1.0)
            stats[mutation] = {
                "avg_sharpe_gain": round(values["sharpe_gain"] / count, 6),
                "avg_fitness_gain": round(values["fitness_gain"] / count, 6),
                "avg_turnover_reduction": round(values["turnover_reduction"] / count, 6),
                "success_rate": round(values["success_count"] / count, 6),
                "count": int(values["count"]),
            }
        stats.update(operator_graph.to_dict())
        self._write_json(self.statistics_file, stats)

    def _ensure_files(self) -> None:
        for path, default in [
            (self.lineage_file, []),
            (self.failures_file, []),
            (self.statistics_file, {}),
        ]:
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                self._write_json(path, default)

    def _read_list(self, path: Path) -> list[dict[str, Any]]:
        data = self._read_json(path, [])
        return data if isinstance(data, list) else []

    def _read_json(self, path: Path, default: Any) -> Any:
        try:
            return safe_read_json(path, default)
        except OSError:
            return default

    def _write_json(self, path: Path, value: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with lock_for_memory_path(path):
            atomic_write_json(path, value)


def classify_failure(text: str) -> str:
    lowered = (text or "").lower()
    if "unit" in lowered:
        return "unit mismatch"
    if "group" in lowered or "bucket" in lowered:
        return "invalid group"
    if "operator" in lowered or "invalid number of inputs" in lowered:
        return "operator misuse"
    if "nan" in lowered:
        return "NaN explosion"
    if "turnover" in lowered:
        return "high turnover"
    if "fitness" in lowered:
        return "low fitness"
    if "unstable" in lowered or "sharpe" in lowered:
        return "unstable signal"
    return "operator misuse"


def _float(value: Any) -> float:
    return finite_float(value)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")
