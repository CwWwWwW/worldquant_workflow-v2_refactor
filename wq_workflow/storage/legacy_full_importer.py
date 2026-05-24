from __future__ import annotations

import csv
import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from .evolution_repository import EvolutionDBRepository


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if number == number and number not in {float("inf"), float("-inf")} else default


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _stable_alpha_id(expression: str) -> str:
    digest = hashlib.sha256("".join(expression.lower().split()).encode("utf-8")).hexdigest()[:20]
    return f"legacy_full_import_{digest}"


class LegacyFullImporter:
    """One-time importer from legacy memories/logs into SQLite canonical evolution memory."""

    def __init__(
        self,
        repository: EvolutionDBRepository | None,
        storage_manager: Any | None = None,
        config: Any | None = None,
    ) -> None:
        self.repository = repository
        self.storage_manager = storage_manager
        self.config = config

    def should_run(self) -> bool:
        if self.repository is None:
            return False
        if not bool(getattr(self.config, "legacy_full_import_enabled", True)):
            return False
        if bool(getattr(self.config, "legacy_full_import_force", False)):
            return True
        if not bool(getattr(self.config, "legacy_full_import_once", True)):
            return True
        completed = self.repository.get_meta("legacy_full_import_completed", "")
        partial = self.repository.get_meta("legacy_full_import_partial", "")
        if str(completed).strip().lower() in {"1", "true", "yes", "on"}:
            return False
        if str(partial).strip().lower() in {"1", "true", "yes", "on"}:
            return True
        return True

    def run_once(
        self,
        *,
        candidate_pool: Any | None = None,
        evolution_memory: Any | None = None,
        log_paths: Iterable[str | Path] | None = None,
    ) -> dict[str, Any]:
        if self.repository is None:
            return {"skipped": True, "reason": "repository_unavailable"}
        if not self.should_run():
            return {"skipped": True, "reason": "already_completed"}

        stats: dict[str, Any] = {
            "seen": 0,
            "normalized": 0,
            "imported_population": 0,
            "imported_policy": 0,
            "imported_graph": 0,
            "imported_lineage": 0,
            "errors": 0,
            "skipped": False,
            "import_attempt_id": hashlib.sha1(_now().encode("utf-8")).hexdigest()[:16],
        }
        try:
            records: list[dict[str, Any]] = []
            source_paths = self._default_log_paths() if log_paths is None else list(log_paths)
            records.extend(self._read_sqlite_legacy_records(stats))
            records.extend(self._read_json_candidate_pool(candidate_pool, stats))
            records.extend(self._read_json_evolution_memory(evolution_memory, stats))
            records.extend(self._read_legacy_logs(source_paths, stats))
            normalized = self._normalize_and_dedupe(records)
            max_records = _int(getattr(self.config, "legacy_full_import_max_records", 0), 0)
            if max_records > 0:
                normalized = normalized[:max_records]
            stats["normalized"] = len(normalized)
            batch_size = max(1, _int(getattr(self.config, "legacy_full_import_batch_size", 1000), 1000))
            for batch in self._chunks(normalized, batch_size):
                try:
                    self._write_batch(batch, stats)
                except Exception:
                    stats["errors"] += len(batch)
                    logging.info("Legacy full import batch failed", exc_info=True)
            self._finalize_import(stats, self._source_hash(source_paths))
            return stats
        except Exception:
            stats["errors"] += 1
            logging.info("Legacy full import failed; falling back to legacy path", exc_info=True)
            self._mark_failed_attempt(stats)
            return stats

    def _read_sqlite_legacy_records(self, stats: dict[str, Any]) -> list[dict[str, Any]]:
        if self.repository is None:
            return []
        conn = self.repository.conn
        records: list[dict[str, Any]] = []
        queries = [
            ("candidate_pool", "SELECT raw_payload, alpha_id, expression, reward, score, passed FROM candidate_pool"),
            ("alpha_runs", "SELECT raw_payload, alpha_id, expression, score AS reward, result FROM alpha_runs"),
            ("lineage", "SELECT raw_payload, child_alpha AS alpha_id, mutation_type FROM lineage"),
            ("evolution_memory", "SELECT memory_value AS raw_payload, memory_key AS alpha_id, score AS reward FROM evolution_memory"),
            ("reward_memory", "SELECT memory_value AS raw_payload, memory_key AS alpha_id, score AS reward FROM reward_memory"),
            ("policy_memory", "SELECT memory_value AS raw_payload, memory_key AS alpha_id, score AS reward FROM policy_memory"),
            ("crossover_memory", "SELECT memory_value AS raw_payload, memory_key AS alpha_id, score AS reward FROM crossover_memory"),
            ("parent_selection_memory", "SELECT memory_value AS raw_payload, memory_key AS alpha_id, score AS reward FROM parent_selection_memory"),
        ]
        for source, sql in queries:
            try:
                for row in conn.execute(sql).fetchall():
                    payload = self._decode_payload(row["raw_payload"] if "raw_payload" in row.keys() else None)
                    if not isinstance(payload, dict):
                        payload = {}
                    for key in row.keys():
                        if key != "raw_payload" and row[key] is not None:
                            payload.setdefault(key, row[key])
                    payload.setdefault("source", source)
                    records.append(payload)
                    stats["seen"] += 1
            except Exception:
                stats["errors"] += 1
                logging.info("Legacy full import skipped SQLite source %s", source, exc_info=True)
        return records

    def _read_json_candidate_pool(self, candidate_pool: Any | None, stats: dict[str, Any]) -> list[dict[str, Any]]:
        if candidate_pool is None or not hasattr(candidate_pool, "_read"):
            return []
        try:
            rows = [dict(row, source="json_candidate_pool") for row in candidate_pool._read() if isinstance(row, dict)]
            stats["seen"] += len(rows)
            return rows
        except Exception:
            stats["errors"] += 1
            logging.info("Legacy full import skipped JSON candidate pool", exc_info=True)
            return []

    def _read_json_evolution_memory(self, evolution_memory: Any | None, stats: dict[str, Any]) -> list[dict[str, Any]]:
        if evolution_memory is None or not hasattr(evolution_memory, "load_recent_history"):
            return []
        try:
            rows = []
            for row in evolution_memory.load_recent_history(limit=2_000_000):
                if not isinstance(row, dict):
                    continue
                rows.append(
                    {
                        **row,
                        "alpha_id": row.get("alpha_id") or row.get("child_alpha"),
                        "expression": row.get("expression_after") or row.get("expression") or row.get("code"),
                        "parent_ids": [row.get("parent_id") or row.get("parent_alpha")],
                        "mutation_history": [row],
                        "source": "json_evolution_memory",
                    }
                )
            stats["seen"] += len(rows)
            return rows
        except Exception:
            stats["errors"] += 1
            logging.info("Legacy full import skipped JSON evolution memory", exc_info=True)
            return []

    def _read_legacy_logs(self, log_paths: Iterable[str | Path], stats: dict[str, Any]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for raw_path in log_paths:
            path = Path(raw_path)
            if not path.exists() or not path.is_file():
                continue
            try:
                if path.suffix.lower() == ".csv":
                    with path.open("r", encoding="utf-8-sig", newline="") as fh:
                        for row in csv.DictReader(fh):
                            if isinstance(row, dict):
                                row["source"] = f"log:{path.name}"
                                rows.append(row)
                else:
                    with path.open("r", encoding="utf-8-sig") as fh:
                        for line in fh:
                            line = line.strip()
                            if not line:
                                continue
                            payload = json.loads(line)
                            if isinstance(payload, dict):
                                payload.setdefault("source", f"log:{path.name}")
                                rows.append(payload)
            except Exception:
                stats["errors"] += 1
                logging.info("Legacy full import skipped log source %s", path, exc_info=True)
        stats["seen"] += len(rows)
        return rows

    def _normalize_and_dedupe(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        best_by_expr: dict[str, dict[str, Any]] = {}
        for raw in records:
            if not isinstance(raw, dict):
                continue
            expr = str(raw.get("expression") or raw.get("alpha") or raw.get("code") or raw.get("expression_after") or "").strip()
            if not expr:
                continue
            reward = _float(raw.get("reward", raw.get("score", raw.get("final_reward", raw.get("effective_reward", 0.0)))))
            metrics = raw.get("metrics") if isinstance(raw.get("metrics"), dict) else self._decode_payload(raw.get("metrics_json"))
            metrics = metrics if isinstance(metrics, dict) else {}
            alpha_id = str(raw.get("alpha_id") or raw.get("id") or _stable_alpha_id(expr))
            item = {
                "alpha_id": alpha_id,
                "expression": expr,
                "reward": reward,
                "survival_score": max(0.0, min(1.0, (reward + 10.0) / 20.0)),
                "family": raw.get("family") or raw.get("behavior_family") or "unknown",
                "behavior_family": raw.get("behavior_family") or raw.get("family") or "unknown",
                "parent_ids": self._as_list(raw.get("parent_ids") or raw.get("parents") or raw.get("parent_id")),
                "mutation_history": self._as_list(raw.get("mutation_history")) or ([raw] if raw.get("mutation_type") else []),
                "lineage_depth": _int(raw.get("lineage_depth", 0), 0),
                "metrics": metrics,
                "birth_source": "legacy_full_import",
                "source": raw.get("source") or "legacy",
                "raw_legacy_payload": raw,
            }
            old = best_by_expr.get("".join(expr.lower().split()))
            if old is None or reward > _float(old.get("reward", 0.0)):
                best_by_expr["".join(expr.lower().split())] = item
        return list(best_by_expr.values())

    def _write_batch(self, batch: list[dict[str, Any]], stats: dict[str, Any]) -> None:
        if self.repository is None or not batch:
            return
        conn = self.repository.conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            for item in batch:
                self.repository.upsert_population_member(item)
                stats["imported_population"] += 1
                reward = _float(item.get("reward", 0.0))
                success = bool(item.get("metrics", {}).get("passed") or reward > 0)
                parent_ids = self._as_list(item.get("parent_ids"))
                for parent_id in parent_ids:
                    if parent_id:
                        self.repository.upsert_graph_edge(
                            "parent_to_child",
                            str(parent_id),
                            str(item.get("alpha_id") or ""),
                            reward=reward,
                            success=success,
                            payload={"source": "legacy_full_import", "import_attempt_id": stats.get("import_attempt_id")},
                        )
                        stats["imported_graph"] += 1
                mutation_history = self._as_list(item.get("mutation_history"))
                for mutation in mutation_history:
                    if not isinstance(mutation, dict):
                        continue
                    action = str(mutation.get("type") or mutation.get("mutation_type") or item.get("mutation_type") or "")
                    if not action:
                        continue
                    self.repository.upsert_policy_action(
                        action_type="mutation",
                        action_name=action,
                        context_key="legacy_full_import",
                        reward_delta=reward,
                        success=success,
                        payload={
                            "source": "legacy_full_import",
                            "alpha_id": item.get("alpha_id"),
                            "import_attempt_id": stats.get("import_attempt_id"),
                        },
                    )
                    stats["imported_policy"] += 1
                self.repository.upsert_lineage_value(
                    str(item.get("alpha_id") or ""),
                    {
                        "current_reward": reward,
                        "future_reward": 0.0,
                        "long_term_value": reward,
                        "descendant_count": 0,
                        "raw_payload": {"source": "legacy_full_import", "import_attempt_id": stats.get("import_attempt_id")},
                    },
                )
                stats["imported_lineage"] += 1
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise

    def _finalize_import(self, stats: dict[str, Any], source_hash: str) -> None:
        if self.repository is None:
            return
        now = _now()
        seen = _int(stats.get("seen", 0), 0)
        imported_population = _int(stats.get("imported_population", 0), 0)
        errors = _int(stats.get("errors", 0), 0)
        self.repository.set_meta("legacy_full_import_last_attempt_at", now)
        self.repository.set_meta("legacy_full_import_last_error_count", str(errors))
        self.repository.set_meta("legacy_full_import_record_count", str(stats.get("seen", 0)))
        self.repository.set_meta("legacy_full_import_imported_population", str(stats.get("imported_population", 0)))
        self.repository.set_meta("legacy_full_import_source_hash", source_hash)
        self.repository.set_meta("legacy_full_import_version", "1")
        self.repository.set_meta("legacy_full_import_errors", str(stats.get("errors", 0)))
        if seen == 0:
            self.repository.set_meta("legacy_full_import_completed", "true")
            self.repository.set_meta("legacy_full_import_partial", "false")
            self.repository.set_meta("legacy_full_import_no_records_found", "true")
            self.repository.set_meta("legacy_full_import_completed_at", now)
            self.repository.set_meta("legacy_full_import_last_status", "no_records_found")
            stats["last_status"] = "no_records_found"
            return
        self.repository.set_meta("legacy_full_import_no_records_found", "false")
        if imported_population <= 0:
            self.repository.set_meta("legacy_full_import_completed", "false")
            self.repository.set_meta("legacy_full_import_partial", "true")
            self.repository.set_meta("legacy_full_import_last_status", "failed_no_population")
            stats["last_status"] = "failed_no_population"
            return
        if errors > 0:
            self.repository.set_meta("legacy_full_import_completed", "false")
            self.repository.set_meta("legacy_full_import_partial", "true")
            self.repository.set_meta("legacy_full_import_last_status", "partial_failed")
            stats["last_status"] = "partial_failed"
            return
        self.repository.set_meta("legacy_full_import_completed", "true")
        self.repository.set_meta("legacy_full_import_partial", "false")
        self.repository.set_meta("legacy_full_import_completed_at", now)
        self.repository.set_meta("legacy_full_import_last_status", "success")
        stats["last_status"] = "success"

    def _write_completion_meta(self, stats: dict[str, Any], source_hash: str) -> None:
        self._finalize_import(stats, source_hash)

    def _mark_failed_attempt(self, stats: dict[str, Any]) -> None:
        if self.repository is None:
            return
        try:
            errors = _int(stats.get("errors", 0), 0)
            imported_population = _int(stats.get("imported_population", 0), 0)
            self.repository.set_meta("legacy_full_import_completed", "false")
            self.repository.set_meta("legacy_full_import_partial", "true")
            self.repository.set_meta("legacy_full_import_last_attempt_at", _now())
            self.repository.set_meta("legacy_full_import_last_error_count", str(errors))
            self.repository.set_meta("legacy_full_import_record_count", str(stats.get("seen", 0)))
            self.repository.set_meta("legacy_full_import_imported_population", str(stats.get("imported_population", 0)))
            self.repository.set_meta(
                "legacy_full_import_last_status",
                "partial_failed" if imported_population > 0 else "failed_no_population",
            )
        except Exception:
            logging.info("Legacy full import failure meta write skipped", exc_info=True)

    def _default_log_paths(self) -> list[Path]:
        try:
            from ..paths import ITERATION_LOG_FILE, LOG_DIR

            paths = [ITERATION_LOG_FILE]
            evolution_dir = LOG_DIR / "evolution"
            if evolution_dir.exists():
                paths.extend(sorted(evolution_dir.glob("*.jsonl")))
            return paths
        except Exception:
            return []

    def _source_hash(self, log_paths: Iterable[str | Path]) -> str:
        digest = hashlib.sha256()
        for raw_path in log_paths:
            path = Path(raw_path)
            try:
                stat = path.stat()
            except OSError:
                continue
            digest.update(str(path).encode("utf-8"))
            digest.update(str(stat.st_size).encode("utf-8"))
            digest.update(str(stat.st_mtime).encode("utf-8"))
        return digest.hexdigest()[:24]

    def _chunks(self, rows: list[dict[str, Any]], size: int) -> Iterable[list[dict[str, Any]]]:
        for index in range(0, len(rows), max(1, size)):
            yield rows[index : index + size]

    def _decode_payload(self, value: Any) -> Any:
        if isinstance(value, (dict, list)):
            return value
        try:
            return json.loads(value or "{}")
        except Exception:
            return {}

    def _as_list(self, value: Any) -> list[Any]:
        if isinstance(value, list):
            return value
        if value is None or value == "":
            return []
        if isinstance(value, str):
            decoded = self._decode_payload(value)
            if isinstance(decoded, list):
                return decoded
        return [value]
