from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from .correlation import extract_structure
from .core.ast import serialize_ast
from .core.parser import ExpressionParser, ParseError
from .core.semantic_similarity import SemanticSimilarity, semantic_signature
from .mutation_engine import complexity_score
from .paths import CANDIDATE_POOL_FILE
from .platform_sc import PLATFORM_SC_METRIC_KEYS, apply_correlation_quality, strong_feedback_allowed
from .safe_io import atomic_write_json, finite_float, safe_json_value, safe_read_json
from .v2_engine import build_behavior_fingerprint, compute_behavior_similarity, estimate_self_corr
from memory.file_locks import candidate_pool_lock


class CandidatePool:
    def __init__(self, path: Path = CANDIDATE_POOL_FILE, max_size: int = 20) -> None:
        self.path = path
        self.max_size = max_size
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write([])

    def add_candidate(
        self,
        *,
        alpha_id: str,
        expression: str,
        metrics: dict[str, float] | None,
        reward: float = 0.0,
        mutation_type: str = "",
        passed: bool = False,
        timestamp: str | None = None,
        reward_breakdown: dict[str, Any] | None = None,
        legacy_reward: float | None = None,
        v2_reward: float | None = None,
        effective_reward: float | None = None,
        migration_state: str = "",
        migration_weights: dict[str, float] | None = None,
        template_success: bool = False,
        template_success_reason: str = "",
        behavior_family: str = "",
        behavior_fingerprint: dict[str, Any] | None = None,
        estimated_self_corr: float | None = None,
        family_reward_inheritance: dict[str, Any] | None = None,
        lineage_depth: int = 0,
        platform_sc_status: str = "",
        platform_sc_max: float | None = None,
        platform_sc_min: float | None = None,
        platform_sc_abs_max: float | None = None,
        platform_sc_payload: dict[str, Any] | None = None,
        enable_v2_metadata: bool = True,
    ) -> dict[str, Any]:
        with candidate_pool_lock:
            return self._add_candidate_locked(
                alpha_id=alpha_id,
                expression=expression,
                metrics=metrics,
                reward=reward,
                mutation_type=mutation_type,
                passed=passed,
                timestamp=timestamp,
                reward_breakdown=reward_breakdown,
                legacy_reward=legacy_reward,
                v2_reward=v2_reward,
                effective_reward=effective_reward,
                migration_state=migration_state,
                migration_weights=migration_weights,
                template_success=template_success,
                template_success_reason=template_success_reason,
                behavior_family=behavior_family,
                behavior_fingerprint=behavior_fingerprint,
                estimated_self_corr=estimated_self_corr,
                family_reward_inheritance=family_reward_inheritance,
                lineage_depth=lineage_depth,
                platform_sc_status=platform_sc_status,
                platform_sc_max=platform_sc_max,
                platform_sc_min=platform_sc_min,
                platform_sc_abs_max=platform_sc_abs_max,
                platform_sc_payload=platform_sc_payload,
                enable_v2_metadata=enable_v2_metadata,
            )

    def _add_candidate_locked(
        self,
        *,
        alpha_id: str,
        expression: str,
        metrics: dict[str, float] | None,
        reward: float = 0.0,
        mutation_type: str = "",
        passed: bool = False,
        timestamp: str | None = None,
        reward_breakdown: dict[str, Any] | None = None,
        legacy_reward: float | None = None,
        v2_reward: float | None = None,
        effective_reward: float | None = None,
        migration_state: str = "",
        migration_weights: dict[str, float] | None = None,
        template_success: bool = False,
        template_success_reason: str = "",
        behavior_family: str = "",
        behavior_fingerprint: dict[str, Any] | None = None,
        estimated_self_corr: float | None = None,
        family_reward_inheritance: dict[str, Any] | None = None,
        lineage_depth: int = 0,
        platform_sc_status: str = "",
        platform_sc_max: float | None = None,
        platform_sc_min: float | None = None,
        platform_sc_abs_max: float | None = None,
        platform_sc_payload: dict[str, Any] | None = None,
        enable_v2_metadata: bool = True,
    ) -> dict[str, Any]:
        rows = self._read()
        fingerprint = _fingerprint(expression)
        rows = [row for row in rows if row.get("fingerprint") != fingerprint]
        ast_payload = _ast_payload(expression, rows)
        ast_fingerprint = str(ast_payload.get("ast_fingerprint") or "")
        if ast_fingerprint:
            rows = [row for row in rows if str(row.get("ast_fingerprint") or "") != ast_fingerprint]
        metrics_payload = apply_correlation_quality(metrics or {})
        candidate = {
            "alpha_id": alpha_id,
            "expression": expression,
            "metrics": metrics_payload,
            "reward": finite_float(reward),
            "mutation_type": mutation_type,
            "passed": bool(passed),
            "template_success": bool(template_success),
            "timestamp": timestamp or _now(),
            "fingerprint": fingerprint,
            "structure": extract_structure(expression),
            "complexity": complexity_score(expression),
            **ast_payload,
        }
        for key in PLATFORM_SC_METRIC_KEYS:
            if key in metrics_payload:
                candidate[key] = metrics_payload.get(key)
        if platform_sc_status:
            candidate["platform_sc_status"] = str(platform_sc_status)
        if platform_sc_max is not None:
            candidate["platform_sc_max"] = finite_float(platform_sc_max)
        if platform_sc_min is not None:
            candidate["platform_sc_min"] = finite_float(platform_sc_min)
        if platform_sc_abs_max is not None:
            candidate["platform_sc_abs_max"] = finite_float(platform_sc_abs_max)
        if platform_sc_payload is not None:
            payload = safe_json_value(platform_sc_payload)
            candidate["platform_sc"] = payload if isinstance(payload, dict) else {}
        if "real_self_corr" in metrics_payload:
            candidate["strong_feedback_allowed"] = strong_feedback_allowed(metrics_payload)
        if enable_v2_metadata:
            v2_fingerprint = behavior_fingerprint or build_behavior_fingerprint(expression)
            estimate = estimate_self_corr(expression, rows, metrics=metrics_payload)
            candidate["behavior_family"] = behavior_family or str(v2_fingerprint.get("family") or "legacy")
            candidate["behavior_fingerprint"] = v2_fingerprint
            candidate["estimated_self_corr"] = (
                finite_float(estimated_self_corr)
                if estimated_self_corr is not None
                else finite_float(estimate.get("estimated_self_corr"))
            )
            candidate["lineage_depth"] = max(0, int(lineage_depth or 0))
            if family_reward_inheritance is not None:
                candidate["family_reward_inheritance"] = family_reward_inheritance
        if template_success_reason:
            candidate["template_success_reason"] = template_success_reason
        if reward_breakdown is not None:
            candidate["reward_breakdown"] = reward_breakdown
        if legacy_reward is not None:
            candidate["legacy_reward"] = finite_float(legacy_reward)
        if v2_reward is not None:
            candidate["v2_reward"] = finite_float(v2_reward)
        if effective_reward is not None:
            candidate["effective_reward"] = finite_float(effective_reward)
        if migration_state:
            candidate["migration_state"] = migration_state
        if migration_weights:
            candidate["migration_weights"] = migration_weights
        rows.append(candidate)
        rows = self._rank_and_trim(rows)
        rows = self._with_diversity(rows)
        self._write(rows)
        try:
            from .storage import get_storage_manager

            get_storage_manager().write_candidate_record(candidate)
        except Exception:
            pass
        return candidate

    def get_top_sharpe(self, limit: int = 5) -> list[dict[str, Any]]:
        return sorted(self._read(), key=lambda row: _metric(row, "sharpe"), reverse=True)[:limit]

    def get_top_fitness(self, limit: int = 5) -> list[dict[str, Any]]:
        return sorted(self._read(), key=lambda row: _metric(row, "fitness"), reverse=True)[:limit]

    def get_diverse_candidates(self, limit: int = 5) -> list[dict[str, Any]]:
        rows = self._with_diversity(self._read())
        rows.sort(key=lambda row: float(row.get("diversity_score", 0.0)), reverse=True)
        return rows[:limit]

    def select_next_parent(self) -> dict[str, Any] | None:
        rows = self._with_diversity(self._read())
        if not rows:
            return None
        rows.sort(key=_selection_score, reverse=True)
        return rows[0]

    def _rank_and_trim(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows.sort(key=_selection_score, reverse=True)
        return rows[: self.max_size]

    def _with_diversity(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        enriched: list[dict[str, Any]] = []
        for row in rows:
            clone = dict(row)
            clone["diversity_score"] = diversity_score(row, rows)
            enriched.append(clone)
        return enriched

    def _read(self) -> list[dict[str, Any]]:
        with candidate_pool_lock:
            data = safe_read_json(self.path, [])
        return data if isinstance(data, list) else []

    def _write(self, rows: list[dict[str, Any]]) -> None:
        with candidate_pool_lock:
            atomic_write_json(self.path, rows)


def diversity_score(candidate: dict[str, Any], pool: list[dict[str, Any]]) -> float:
    if len(pool) <= 1:
        return 1.0
    semantic = _semantic_diversity(candidate, pool)
    behavior = _behavior_diversity(candidate, pool)
    if semantic is not None and behavior is not None:
        return round(semantic * 0.45 + behavior * 0.55, 6)
    if semantic is not None:
        return semantic
    if behavior is not None:
        return behavior
    current = _features(candidate)
    distances = [_feature_distance(current, _features(other)) for other in pool if other is not candidate]
    return round(sum(distances) / max(len(distances), 1), 6)


def _features(candidate: dict[str, Any]) -> dict[str, set[str]]:
    expression = str(candidate.get("expression") or "")
    structure = candidate.get("structure") if isinstance(candidate.get("structure"), dict) else extract_structure(expression)
    functions = {str(item).lower() for item in structure.get("functions", [])}
    windows = {str(item) for item in structure.get("windows", [])}
    groups = {str(item).lower() for item in structure.get("groups", [])}
    signal_fields = set(re.findall(r"\b(close|open|high|low|volume|vwap|returns|cap)\b", expression, re.I))
    neutralizations = {item for item in functions if item.startswith("group_") or item == "bucket"}
    return {
        "operators": functions,
        "windows": windows,
        "groups": groups,
        "signal_fields": {item.lower() for item in signal_fields},
        "neutralizations": neutralizations,
    }


def _feature_distance(left: dict[str, set[str]], right: dict[str, set[str]]) -> float:
    weights = {
        "operators": 0.35,
        "signal_fields": 0.25,
        "neutralizations": 0.20,
        "windows": 0.10,
        "groups": 0.10,
    }
    score = 0.0
    for key, weight in weights.items():
        score += (1.0 - _jaccard(left.get(key, set()), right.get(key, set()))) * weight
    return score


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left and not right:
        return 1.0
    return len(left & right) / max(len(left | right), 1)


def _selection_score(row: dict[str, Any]) -> float:
    metrics = row.get("metrics") if isinstance(row.get("metrics"), dict) else {}
    reward = _float(row.get("reward"))
    sharpe = _float(metrics.get("sharpe"))
    fitness = _float(metrics.get("fitness"))
    diversity = _float(row.get("diversity_score"))
    similarity_penalty = _float(row.get("max_semantic_similarity")) * 0.08
    real_sc = _float(_first_present(row.get("real_self_corr"), metrics.get("real_self_corr"), metrics.get("platform_sc_abs_max")))
    estimated_sc = _float(_first_present(row.get("estimated_self_corr"), metrics.get("estimated_self_corr")))
    if real_sc >= 0.90:
        similarity_penalty += 1.2
    elif real_sc >= 0.85:
        similarity_penalty += 0.75
    elif real_sc > 0.70:
        similarity_penalty += 0.35
    elif estimated_sc >= 0.75:
        similarity_penalty += 0.15
    recent = _recency_score(str(row.get("timestamp") or ""))
    passed_bonus = 0.25 if row.get("passed") else 0.0
    if row.get("submission_quality") in {"bad_sc", "blocked_by_sc"}:
        passed_bonus = 0.0
    return reward * 0.45 + sharpe * 0.2 + fitness * 0.15 + diversity * 0.18 + recent * 0.1 + passed_bonus - similarity_penalty


def _recency_score(timestamp: str) -> float:
    if not timestamp:
        return 0.0
    try:
        age = datetime.now() - datetime.fromisoformat(timestamp)
    except ValueError:
        return 0.0
    return max(0.0, 1.0 - age.total_seconds() / (7 * 24 * 3600))


def _metric(row: dict[str, Any], key: str) -> float:
    metrics = row.get("metrics") if isinstance(row.get("metrics"), dict) else {}
    return _float(metrics.get(key))


def _float(value: Any) -> float:
    return finite_float(value)


def _first_present(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _fingerprint(expression: str) -> str:
    return re.sub(r"\s+", "", (expression or "").lower())


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _ast_payload(expression: str, existing_rows: list[dict[str, Any]]) -> dict[str, Any]:
    parser = ExpressionParser()
    try:
        ast = parser.parse(expression)
    except ParseError:
        return {
            "ast_parseable": False,
            "ast_fingerprint": "",
            "semantic_signature": {},
            "max_semantic_similarity": 0.0,
        }
    similarity = SemanticSimilarity()
    max_score = 0.0
    for row in existing_rows:
        other_expression = str(row.get("expression") or "")
        try:
            other_ast = parser.parse(other_expression)
        except ParseError:
            continue
        max_score = max(max_score, similarity.similarity(ast, other_ast))
    return {
        "ast_parseable": True,
        "ast_fingerprint": _fingerprint(serialize_ast(ast)),
        "semantic_signature": semantic_signature(ast),
        "max_semantic_similarity": round(max_score, 6),
    }


def _semantic_diversity(candidate: dict[str, Any], pool: list[dict[str, Any]]) -> float | None:
    if not candidate.get("ast_parseable"):
        return None
    parser = ExpressionParser()
    similarity = SemanticSimilarity()
    try:
        current = parser.parse(str(candidate.get("expression") or ""))
    except ParseError:
        return None
    distances: list[float] = []
    for other in pool:
        if other is candidate or not other.get("ast_parseable"):
            continue
        try:
            other_ast = parser.parse(str(other.get("expression") or ""))
        except ParseError:
            continue
        distances.append(1.0 - similarity.similarity(current, other_ast))
    if not distances:
        return None
    return round(sum(distances) / len(distances), 6)


def _behavior_diversity(candidate: dict[str, Any], pool: list[dict[str, Any]]) -> float | None:
    current = candidate.get("behavior_fingerprint")
    if not isinstance(current, dict):
        current = build_behavior_fingerprint(str(candidate.get("expression") or ""))
    distances: list[float] = []
    for other in pool:
        if other is candidate:
            continue
        other_fp = other.get("behavior_fingerprint")
        if not isinstance(other_fp, dict):
            other_fp = build_behavior_fingerprint(str(other.get("expression") or ""))
        distances.append(1.0 - compute_behavior_similarity(current, other_fp))
    if not distances:
        return None
    return round(sum(distances) / len(distances), 6)
