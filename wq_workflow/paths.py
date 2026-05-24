from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

CONFIG_FILE = ROOT / "config.json"
COOKIE_FILE = ROOT / "cookies.json"
LOCAL_LIBRARY_FILE = ROOT / "local_alpha_library.csv"
ITERATION_LOG_FILE = ROOT / "iteration_log.csv"
FAVORITE_LOG_FILE = ROOT / "favorite_alphas.csv"
CORRELATION_LOG_FILE = ROOT / "correlation_check.log"
WORKFLOW_LOG_FILE = ROOT / "workflow.log"
RUNTIME_DIR = ROOT / "runtime"
DB_DIR = RUNTIME_DIR / "db"
WORKFLOW_DB_FILE = DB_DIR / "workflow.db"

INPUT_TEMPLATE_DIR = ROOT / "input_templates"
TEMPLATE_DIR = ROOT / "templates"
SPLIT_MANIFEST_FILE = TEMPLATE_DIR / "last_split_manifest.json"
ITERATION_DIR = ROOT / "iterations"
FAVORITE_DIR = ROOT / "favorites"
LOG_DIR = ROOT / "logs"
EVOLUTION_LOG_DIR = LOG_DIR / "evolution"
FAILURE_DIR = LOG_DIR / "failures"
TRACE_DIR = LOG_DIR / "traces"
STATE_LOG_FILE = LOG_DIR / "workflow_state.jsonl"
REWARD_SHADOW_LOG_DIR = ROOT / "reward_shadow_logs"
MIGRATION_LOG_DIR = ROOT / "migration_logs"
MEMORY_DIR = ROOT / "memory"
EVOLUTION_MEMORY_DIR = MEMORY_DIR / "evolution"
FAILURE_PATTERN_DIR = MEMORY_DIR / "failure_patterns"
STATISTICS_MEMORY_DIR = MEMORY_DIR / "statistics"
DASHBOARD_SNAPSHOT_DIR = MEMORY_DIR / "dashboard_snapshot"
INSIGHT_MEMORY_DIR = MEMORY_DIR / "insights"

ALPHA_LINEAGE_FILE = EVOLUTION_MEMORY_DIR / "alpha_lineage.json"
CANDIDATE_POOL_FILE = EVOLUTION_MEMORY_DIR / "candidate_pool.json"
MIGRATION_STATE_FILE = EVOLUTION_MEMORY_DIR / "migration_state.json"
MIGRATION_METRICS_FILE = EVOLUTION_MEMORY_DIR / "migration_metrics.json"
SURVIVAL_MEMORY_FILE = EVOLUTION_MEMORY_DIR / "survival_memory.json"
PENDING_REWARDS_FILE = EVOLUTION_MEMORY_DIR / "pending_rewards.json"
TEMPLATE_STATS_FILE = EVOLUTION_MEMORY_DIR / "template_stats.json"
SIDECAR_STATE_FILE = EVOLUTION_MEMORY_DIR / "sidecar_state.json"
POPULATION_OVERLAY_STATE_FILE = EVOLUTION_MEMORY_DIR / "population_overlay_state.json"
POLICY_HINT_STATE_FILE = EVOLUTION_MEMORY_DIR / "policy_hint_state.json"
SIMULATOR_OBSERVER_STATE_FILE = EVOLUTION_MEMORY_DIR / "simulator_observer_state.json"
SURVIVAL_LOG_FILE = EVOLUTION_LOG_DIR / "survival.log"
PENDING_REWARD_LOG_FILE = EVOLUTION_LOG_DIR / "pending_reward.log"
FAMILY_POPULATION_LOG_FILE = EVOLUTION_LOG_DIR / "family_population.log"
TEMPLATE_POPULATION_LOG_FILE = FAMILY_POPULATION_LOG_FILE
ADAPTIVE_WEIGHT_LOG_FILE = EVOLUTION_LOG_DIR / "adaptive_weight.log"
SIDECAR_ADVISORY_LOG_FILE = EVOLUTION_LOG_DIR / "sidecar_advisory.jsonl"
AST_EVOLUTION_FAILURE_LOG_FILE = EVOLUTION_LOG_DIR / "ast_evolution_failures.jsonl"
SNAPSHOT_CANDIDATE_POOL_FILE = DASHBOARD_SNAPSHOT_DIR / "candidate_pool.snapshot.json"
SNAPSHOT_ALPHA_LINEAGE_FILE = DASHBOARD_SNAPSHOT_DIR / "alpha_lineage.snapshot.json"
SNAPSHOT_MIGRATION_STATE_FILE = DASHBOARD_SNAPSHOT_DIR / "migration_state.snapshot.json"
SNAPSHOT_MIGRATION_METRICS_FILE = DASHBOARD_SNAPSHOT_DIR / "migration_metrics.snapshot.json"
FAILURE_PATTERNS_FILE = FAILURE_PATTERN_DIR / "failures.json"
OPERATOR_STATISTICS_FILE = STATISTICS_MEMORY_DIR / "operator_statistics.json"
RESEARCH_INSIGHTS_FILE = INSIGHT_MEMORY_DIR / "research_insights.json"
INSIGHT_STATE_FILE = INSIGHT_MEMORY_DIR / "insight_state.json"


LOCAL_LIBRARY_FIELDS = [
    "alpha_id",
    "created_at",
    "md5",
    "code",
    "core_structure",
    "metrics",
    "returns_path",
    "behavior_family",
    "behavior_fingerprint",
    "estimated_self_corr",
    "platform_sc_status",
    "platform_sc_max",
    "platform_sc_min",
    "platform_sc_abs_max",
    "real_self_corr",
    "sc_source",
    "correlation_quality",
    "submission_quality",
    "platform_sc_json",
]

ITERATION_LOG_FIELDS = [
    "time",
    "template_file",
    "alpha_name",
    "iteration",
    "stage",
    "code",
    "platform_error",
    "quality_json",
    "metrics_json",
    "ds_response",
    "screenshot",
    "behavior_family",
    "estimated_self_corr",
    "platform_sc_status",
    "platform_sc_max",
    "platform_sc_min",
    "platform_sc_abs_max",
    "real_self_corr",
    "sc_source",
    "correlation_quality",
    "submission_quality",
    "platform_sc_json",
]

FAVORITE_LOG_FIELDS = [
    "time",
    "template_file",
    "alpha_name",
    "code",
    "metrics_json",
    "quality_json",
    "screenshot",
    "platform_sc_status",
    "platform_sc_max",
    "platform_sc_min",
    "platform_sc_abs_max",
    "platform_sc_json",
]


def now_ts() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def ensure_dirs() -> None:
    for directory in [
        INPUT_TEMPLATE_DIR,
        TEMPLATE_DIR,
        ITERATION_DIR,
        FAVORITE_DIR,
        LOG_DIR,
        EVOLUTION_LOG_DIR,
        FAILURE_DIR,
        TRACE_DIR,
        REWARD_SHADOW_LOG_DIR,
        MIGRATION_LOG_DIR,
        EVOLUTION_MEMORY_DIR,
        FAILURE_PATTERN_DIR,
        STATISTICS_MEMORY_DIR,
        DASHBOARD_SNAPSHOT_DIR,
        INSIGHT_MEMORY_DIR,
        RUNTIME_DIR,
        DB_DIR,
    ]:
        directory.mkdir(parents=True, exist_ok=True)


def ensure_json_file(path: Path, default: Any) -> None:
    if not path.exists():
        from .safe_io import atomic_write_json

        atomic_write_json(path, default, make_backup=False)


def json_dumps(value: Any) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def ensure_csv(path: Path, fields: list[str]) -> list[str]:
    if not path.exists():
        with path.open("w", newline="", encoding="utf-8") as fh:
            csv.DictWriter(fh, fieldnames=fields).writeheader()
        return list(fields)
    with path.open("r", newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        header = list(reader.fieldnames or [])
        rows = [dict(row) for row in reader]
    if not header:
        with path.open("w", newline="", encoding="utf-8") as fh:
            csv.DictWriter(fh, fieldnames=fields).writeheader()
        return list(fields)
    effective_fields = list(header)
    for field in fields:
        if field not in effective_fields:
            effective_fields.append(field)
    if effective_fields != header:
        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=effective_fields, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                writer.writerow({field: row.get(field, "") for field in effective_fields})
    return effective_fields


def append_csv(path: Path, fields: list[str], row: dict[str, Any]) -> None:
    effective_fields = ensure_csv(path, fields)
    with path.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=effective_fields, extrasaction="ignore")
        writer.writerow({field: row.get(field, "") for field in effective_fields})


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def ensure_runtime_files() -> None:
    ensure_dirs()
    ensure_csv(LOCAL_LIBRARY_FILE, LOCAL_LIBRARY_FIELDS)
    ensure_csv(ITERATION_LOG_FILE, ITERATION_LOG_FIELDS)
    ensure_csv(FAVORITE_LOG_FILE, FAVORITE_LOG_FIELDS)
    ensure_json_file(ALPHA_LINEAGE_FILE, [])
    ensure_json_file(CANDIDATE_POOL_FILE, [])
    ensure_json_file(MIGRATION_STATE_FILE, {})
    ensure_json_file(MIGRATION_METRICS_FILE, {})
    ensure_json_file(SURVIVAL_MEMORY_FILE, {"version": "1.1.6", "data": {}})
    ensure_json_file(PENDING_REWARDS_FILE, {"version": "1.1.6", "data": {}})
    ensure_json_file(TEMPLATE_STATS_FILE, {"version": "1.1.6", "data": {}})
    ensure_json_file(SIDECAR_STATE_FILE, {"version": "1.2.0", "mode": "sidecar_advisory", "data": {}})
    ensure_json_file(POPULATION_OVERLAY_STATE_FILE, {"version": "1.2.0", "data": {}})
    ensure_json_file(POLICY_HINT_STATE_FILE, {"version": "1.2.0", "data": {}})
    ensure_json_file(SIMULATOR_OBSERVER_STATE_FILE, {"version": "1.2.0", "data": {}})
    ensure_json_file(FAILURE_PATTERNS_FILE, [])
    ensure_json_file(OPERATOR_STATISTICS_FILE, {})
    ensure_json_file(RESEARCH_INSIGHTS_FILE, [])
    ensure_json_file(INSIGHT_STATE_FILE, {"schema_version": "1.0"})
    SURVIVAL_LOG_FILE.touch(exist_ok=True)
    PENDING_REWARD_LOG_FILE.touch(exist_ok=True)
    TEMPLATE_POPULATION_LOG_FILE.touch(exist_ok=True)
    FAMILY_POPULATION_LOG_FILE.touch(exist_ok=True)
    ADAPTIVE_WEIGHT_LOG_FILE.touch(exist_ok=True)
    SIDECAR_ADVISORY_LOG_FILE.touch(exist_ok=True)
    AST_EVOLUTION_FAILURE_LOG_FILE.touch(exist_ok=True)
    CORRELATION_LOG_FILE.touch(exist_ok=True)
    WORKFLOW_LOG_FILE.touch(exist_ok=True)
