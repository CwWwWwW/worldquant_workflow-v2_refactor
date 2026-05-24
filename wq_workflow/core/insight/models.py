from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


INSIGHT_SCHEMA_VERSION = "1.0"


@dataclass
class ResearchSample:
    sample_id: str
    alpha_id: str
    expression: str
    operators: list[str]
    fields: list[str]
    windows: list[int]
    metrics: dict[str, float]
    reward: float
    passed: bool
    quality_passed: bool
    failure_type: str
    family: str
    survival_rounds: int
    estimated_self_corr: float
    source_round: int
    timestamp: str

    @property
    def successful(self) -> bool:
        return self.reward > 0 or self.passed or self.quality_passed

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_id": self.sample_id,
            "alpha_id": self.alpha_id,
            "expression": self.expression,
            "operators": list(self.operators),
            "fields": list(self.fields),
            "windows": list(self.windows),
            "metrics": dict(self.metrics),
            "reward": self.reward,
            "passed": self.passed,
            "quality_passed": self.quality_passed,
            "failure_type": self.failure_type,
            "family": self.family,
            "survival_rounds": self.survival_rounds,
            "estimated_self_corr": self.estimated_self_corr,
            "source_round": self.source_round,
            "timestamp": self.timestamp,
        }


@dataclass
class ResearchCluster:
    id: str
    type: str
    key: str
    support_count: int
    contradiction_count: int
    avg_reward: float
    avg_metrics: dict[str, float]
    operators: list[str]
    families: list[str]
    failure_types: list[str]
    source_rounds: list[int]
    examples: list[str]
    market_tags: list[str] = field(default_factory=list)

    def to_prompt_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "key": self.key,
            "support_count": self.support_count,
            "contradiction_count": self.contradiction_count,
            "avg_reward": round(self.avg_reward, 6),
            "avg_metrics": {key: round(value, 6) for key, value in self.avg_metrics.items()},
            "operators": self.operators[:10],
            "families": self.families[:6],
            "failure_types": self.failure_types[:6],
            "source_rounds": self.source_rounds[-12:],
            "examples": self.examples[:3],
            "market_tags": self.market_tags[:8],
        }


@dataclass
class ResearchInsight:
    id: str
    type: str
    summary: str
    confidence: float
    support_count: int
    contradiction_count: int
    freshness_score: float
    decay_score: float
    source_rounds: list[int]
    related_operators: list[str]
    market_tags: list[str]
    created_at: str
    updated_at: str
    schema_version: str = INSIGHT_SCHEMA_VERSION
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ResearchInsight":
        known = {
            "id",
            "type",
            "summary",
            "confidence",
            "support_count",
            "contradiction_count",
            "freshness_score",
            "decay_score",
            "source_rounds",
            "related_operators",
            "market_tags",
            "created_at",
            "updated_at",
            "schema_version",
        }
        return cls(
            id=str(payload.get("id") or ""),
            type=str(payload.get("type") or "general"),
            summary=str(payload.get("summary") or ""),
            confidence=_float(payload.get("confidence")),
            support_count=_int(payload.get("support_count")),
            contradiction_count=_int(payload.get("contradiction_count")),
            freshness_score=_float(payload.get("freshness_score")),
            decay_score=_float(payload.get("decay_score")),
            source_rounds=_int_list(payload.get("source_rounds")),
            related_operators=_str_list(payload.get("related_operators")),
            market_tags=_str_list(payload.get("market_tags")),
            created_at=str(payload.get("created_at") or ""),
            updated_at=str(payload.get("updated_at") or ""),
            schema_version=str(payload.get("schema_version") or INSIGHT_SCHEMA_VERSION),
            extra={str(key): value for key, value in payload.items() if key not in known},
        )

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "type": self.type,
            "summary": self.summary,
            "confidence": round(_clamp(self.confidence), 6),
            "support_count": max(0, int(self.support_count)),
            "contradiction_count": max(0, int(self.contradiction_count)),
            "freshness_score": round(_clamp(self.freshness_score), 6),
            "decay_score": round(_clamp(self.decay_score), 6),
            "source_rounds": sorted({int(item) for item in self.source_rounds if int(item) >= 0}),
            "related_operators": [item for item in self.related_operators if item],
            "market_tags": [item for item in self.market_tags if item],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "schema_version": self.schema_version or INSIGHT_SCHEMA_VERSION,
        }
        payload.update(self.extra)
        return payload


def _float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number != number or number in {float("inf"), float("-inf")}:
        return default
    return number


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _int_list(value: Any) -> list[int]:
    if not isinstance(value, list):
        return []
    result: list[int] = []
    for item in value:
        try:
            result.append(int(item))
        except (TypeError, ValueError):
            continue
    return result


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, _float(value)))
