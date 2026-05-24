from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from ...paths import SURVIVAL_LOG_FILE, SURVIVAL_MEMORY_FILE
from ...safe_io import append_jsonl, finite_float
from .versioned_memory import VersionedEvolutionMemory


class SurvivalMemoryManager:
    def __init__(
        self,
        path: Path = SURVIVAL_MEMORY_FILE,
        log_path: Path = SURVIVAL_LOG_FILE,
    ) -> None:
        self.path = path
        self.log_path = log_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._store = VersionedEvolutionMemory(self.path)

    def load_memory(self) -> dict[str, dict[str, Any]]:
        payload = self._store.load_data()
        return {str(key): self._normalize_record(value) for key, value in payload.items() if isinstance(value, dict)}

    def save_memory(self, memory: dict[str, dict[str, Any]]) -> None:
        cleaned = {str(key): self._normalize_record(value) for key, value in memory.items() if isinstance(value, dict)}
        self._store.save_data(cleaned)

    def flush(self) -> None:
        self._store.flush()

    def close(self) -> None:
        self._store.close()

    def register_alpha(
        self,
        alpha_id: str,
        *,
        generation_created: int = 0,
        behavior_family: str = "",
        template: str = "",
        operator: str = "",
        parent: str = "",
        lineage_depth: int = 0,
    ) -> dict[str, Any]:
        if not alpha_id:
            return {}
        memory = self.load_memory()
        record = memory.get(alpha_id)
        if not isinstance(record, dict):
            record = {
                "generation_created": max(0, int(generation_created or 0)),
                "survival_rounds": 0,
                "pass_count": 0,
                "fail_count": 0,
                "decay_score": 0.0,
                "behavior_family": behavior_family or template or "legacy",
                "operator": operator or "unknown",
                "parent": parent or "",
                "children_success": 0,
                "lineage_depth": max(0, int(lineage_depth or 0)),
                "long_term_score": 0.0,
            }
        else:
            record = self._normalize_record(record)
            record.setdefault("generation_created", max(0, int(generation_created or 0)))
            record["behavior_family"] = behavior_family or template or str(record.get("behavior_family") or record.get("template") or "legacy")
            record["operator"] = operator or str(record.get("operator") or "unknown")
            record["parent"] = parent or str(record.get("parent") or "")
            record["lineage_depth"] = max(int(record.get("lineage_depth") or 0), int(lineage_depth or 0))
        record["long_term_score"] = self.compute_long_term_score(record)
        memory[alpha_id] = record
        self.save_memory(memory)
        self._log("register_alpha", alpha_id, record)
        return dict(record)

    def update_survival(self, alpha_id: str, *, passed: bool) -> dict[str, Any]:
        if not alpha_id:
            return {}
        memory = self.load_memory()
        record = memory.setdefault(alpha_id, self._default_record())
        record = self._normalize_record(record)
        if passed:
            record["survival_rounds"] = max(0, int(record.get("survival_rounds") or 0)) + 1
            record["pass_count"] = max(0, int(record.get("pass_count") or 0)) + 1
        else:
            record["fail_count"] = max(0, int(record.get("fail_count") or 0)) + 1
        record["decay_score"] = self._computed_decay(record)
        record["long_term_score"] = self.compute_long_term_score(record)
        memory[alpha_id] = record
        self.save_memory(memory)
        self._log("update_survival", alpha_id, record)
        return dict(record)

    def update_decay(self, alpha_id: str, decay_score: float | None = None) -> dict[str, Any]:
        if not alpha_id:
            return {}
        memory = self.load_memory()
        record = memory.setdefault(alpha_id, self._default_record())
        record = self._normalize_record(record)
        record["decay_score"] = (
            max(0.0, finite_float(decay_score))
            if decay_score is not None
            else self._computed_decay(record)
        )
        record["long_term_score"] = self.compute_long_term_score(record)
        memory[alpha_id] = record
        self.save_memory(memory)
        self._log("update_decay", alpha_id, record)
        return dict(record)

    def increment_children_success(self, alpha_id: str) -> dict[str, Any]:
        if not alpha_id:
            return {}
        memory = self.load_memory()
        record = memory.setdefault(alpha_id, self._default_record())
        record = self._normalize_record(record)
        record["children_success"] = max(0, int(record.get("children_success") or 0)) + 1
        record["long_term_score"] = self.compute_long_term_score(record)
        memory[alpha_id] = record
        self.save_memory(memory)
        self._log("increment_children_success", alpha_id, record)
        return dict(record)

    def compute_long_term_score(self, alpha_or_record: str | dict[str, Any]) -> float:
        if isinstance(alpha_or_record, str):
            record = self.load_memory().get(alpha_or_record, {})
        else:
            record = alpha_or_record
        score = (
            max(0, int(record.get("survival_rounds") or 0)) * 0.15
            + max(0, int(record.get("children_success") or 0)) * 0.2
            - max(0.0, finite_float(record.get("decay_score"))) * 0.3
            + max(0, int(record.get("lineage_depth") or 0)) * 0.05
        )
        return round(score, 6)

    def _default_record(self) -> dict[str, Any]:
        return {
            "generation_created": 0,
            "survival_rounds": 0,
            "pass_count": 0,
            "fail_count": 0,
            "decay_score": 0.0,
            "behavior_family": "legacy",
            "operator": "unknown",
            "parent": "",
            "children_success": 0,
            "lineage_depth": 0,
            "long_term_score": 0.0,
        }

    def _normalize_record(self, record: dict[str, Any]) -> dict[str, Any]:
        result = dict(record)
        result["generation_created"] = max(0, int(result.get("generation_created") or 0))
        result["survival_rounds"] = max(0, int(result.get("survival_rounds") or 0))
        result["pass_count"] = max(0, int(result.get("pass_count") or 0))
        result["fail_count"] = max(0, int(result.get("fail_count") or 0))
        result["decay_score"] = max(0.0, finite_float(result.get("decay_score")))
        result["behavior_family"] = str(result.get("behavior_family") or result.get("template") or "legacy")
        result["operator"] = str(result.get("operator") or "unknown")
        result["parent"] = str(result.get("parent") or "")
        result["children_success"] = max(0, int(result.get("children_success") or 0))
        result["lineage_depth"] = max(0, int(result.get("lineage_depth") or 0))
        result["long_term_score"] = self.compute_long_term_score(result)
        return result

    def _computed_decay(self, record: dict[str, Any]) -> float:
        passes = max(0, int(record.get("pass_count") or 0))
        fails = max(0, int(record.get("fail_count") or 0))
        total = passes + fails
        if total <= 0:
            return 0.0
        return round(fails / total, 6)

    def _log(self, event: str, alpha_id: str, record: dict[str, Any]) -> None:
        append_jsonl(
            self.log_path,
            {
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "event": event,
                "alpha_id": alpha_id,
                "record": record,
            },
        )
