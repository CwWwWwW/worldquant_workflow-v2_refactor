from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
from typing import Iterable

from ...safe_io import finite_float
from .models import ResearchCluster, ResearchSample


class InsightClusterer:
    def cluster(self, samples: list[ResearchSample]) -> list[ResearchCluster]:
        if not samples:
            return []
        clusters: list[ResearchCluster] = []
        clusters.extend(self._operator_combo_clusters(samples))
        clusters.extend(self._reward_pattern_clusters(samples))
        clusters.extend(self._regime_clusters(samples))
        clusters.extend(self._failure_clusters(samples))
        clusters.extend(self._family_clusters(samples))
        clusters.sort(key=lambda item: (item.support_count, item.avg_reward, -item.contradiction_count), reverse=True)
        return clusters

    def _operator_combo_clusters(self, samples: list[ResearchSample]) -> list[ResearchCluster]:
        grouped: dict[str, list[ResearchSample]] = defaultdict(list)
        for sample in samples:
            key = "+".join(sorted(set(sample.operators))[:5]) or "unknown"
            grouped[key].append(sample)
        return [
            self._build_cluster("operator_combo", key, rows)
            for key, rows in grouped.items()
            if _successful_count(rows) > 0 and len(rows) >= 2
        ]

    def _reward_pattern_clusters(self, samples: list[ResearchSample]) -> list[ResearchCluster]:
        grouped: dict[str, list[ResearchSample]] = defaultdict(list)
        for sample in samples:
            if not sample.successful:
                continue
            bucket = _reward_bucket(sample.reward)
            grouped[f"{sample.family}:{bucket}:{_turnover_bucket(sample)}"].append(sample)
        return [self._build_cluster("reward_pattern", key, rows) for key, rows in grouped.items() if len(rows) >= 1]

    def _regime_clusters(self, samples: list[ResearchSample]) -> list[ResearchCluster]:
        grouped: dict[str, list[ResearchSample]] = defaultdict(list)
        for sample in samples:
            if not sample.successful:
                continue
            grouped[f"{sample.family}:{_window_bucket(sample)}:{_neutralization_tag(sample)}"].append(sample)
        return [self._build_cluster("regime", key, rows) for key, rows in grouped.items() if len(rows) >= 1]

    def _failure_clusters(self, samples: list[ResearchSample]) -> list[ResearchCluster]:
        grouped: dict[str, list[ResearchSample]] = defaultdict(list)
        for sample in samples:
            if sample.successful or not sample.failure_type:
                continue
            combo = "+".join(sorted(set(sample.operators))[:4]) or "unknown"
            grouped[f"{sample.failure_type}:{sample.family}:{combo}"].append(sample)
        return [self._build_cluster("failure_pattern", key, rows) for key, rows in grouped.items() if len(rows) >= 1]

    def _family_clusters(self, samples: list[ResearchSample]) -> list[ResearchCluster]:
        grouped: dict[str, list[ResearchSample]] = defaultdict(list)
        for sample in samples:
            grouped[sample.family or "legacy"].append(sample)
        return [
            self._build_cluster("family_pattern", key, rows)
            for key, rows in grouped.items()
            if _successful_count(rows) > 0 and len(rows) >= 2
        ]

    def _build_cluster(self, cluster_type: str, key: str, rows: list[ResearchSample]) -> ResearchCluster:
        successes = [sample for sample in rows if sample.successful]
        failures = [sample for sample in rows if not sample.successful]
        support_count = len(successes) if cluster_type != "failure_pattern" else len(failures)
        contradiction_count = len(failures) if cluster_type != "failure_pattern" else len(successes)
        operators = _top_values(operator for sample in rows for operator in sample.operators)
        families = _top_values(sample.family for sample in rows if sample.family)
        failure_types = _top_values(sample.failure_type for sample in rows if sample.failure_type)
        source_rounds = sorted({sample.source_round for sample in rows if sample.source_round >= 0})
        examples = [_shorten(sample.expression) for sample in rows[:3] if sample.expression]
        return ResearchCluster(
            id=_cluster_id(cluster_type, key),
            type=cluster_type,
            key=key,
            support_count=support_count,
            contradiction_count=contradiction_count,
            avg_reward=_avg(sample.reward for sample in rows),
            avg_metrics=_avg_metrics(rows),
            operators=operators,
            families=families,
            failure_types=failure_types,
            source_rounds=source_rounds,
            examples=examples,
            market_tags=_market_tags(rows),
        )


def _successful_count(samples: list[ResearchSample]) -> int:
    return sum(1 for sample in samples if sample.successful)


def _reward_bucket(reward: float) -> str:
    if reward >= 1.0:
        return "strong_positive"
    if reward > 0:
        return "positive"
    if reward <= -0.5:
        return "negative"
    return "neutral"


def _turnover_bucket(sample: ResearchSample) -> str:
    turnover = finite_float(sample.metrics.get("turnover"))
    if turnover >= 65:
        return "high_turnover"
    if turnover >= 25:
        return "medium_turnover"
    if turnover > 0:
        return "low_turnover"
    return "unknown_turnover"


def _window_bucket(sample: ResearchSample) -> str:
    if not sample.windows:
        return "no_window"
    high = max(sample.windows)
    if high <= 8:
        return "short_window"
    if high <= 30:
        return "medium_window"
    return "long_window"


def _neutralization_tag(sample: ResearchSample) -> str:
    operators = set(sample.operators)
    if "group_neutralize" in operators:
        return "group_neutralize"
    if "group_zscore" in operators:
        return "group_zscore"
    if "group_rank" in operators:
        return "group_rank"
    if "bucket" in operators:
        return "bucket"
    return "no_neutralization"


def _top_values(values: Iterable[str], limit: int = 8) -> list[str]:
    counter = Counter(value for value in values if value)
    return [value for value, _count in counter.most_common(limit)]


def _avg(values: Iterable[float]) -> float:
    rows = [finite_float(value) for value in values]
    return round(sum(rows) / max(len(rows), 1), 6)


def _avg_metrics(samples: list[ResearchSample]) -> dict[str, float]:
    keys = sorted({key for sample in samples for key in sample.metrics})
    result: dict[str, float] = {}
    for key in keys:
        values = [finite_float(sample.metrics.get(key)) for sample in samples if key in sample.metrics]
        if values:
            result[key] = round(sum(values) / len(values), 6)
    return result


def _market_tags(samples: list[ResearchSample]) -> list[str]:
    tags = set()
    group_fields = {"market", "sector", "industry", "subindustry", "exchange"}
    for sample in samples:
        tags.update(field for field in sample.fields if field in group_fields)
        if sample.family:
            tags.add(sample.family)
    return sorted(tags)[:8]


def _cluster_id(cluster_type: str, key: str) -> str:
    digest = hashlib.sha1(f"{cluster_type}|{key}".encode("utf-8", errors="ignore")).hexdigest()
    return f"{cluster_type}:{digest[:12]}"


def _shorten(text: str, limit: int = 220) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3] + "..."
