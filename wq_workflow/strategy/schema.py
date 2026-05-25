from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from wq_workflow.data.json_utils import safe_float, safe_int, to_jsonable

STRATEGY_TYPES = {
    "legacy_baseline",
    "random_exploration",
    "experiment_budget",
    "ml_parent_policy",
    "ml_mutation_policy",
    "replay_supported_policy",
    "counterfactual_supported_policy",
    "governance_safe_policy",
    "manual_or_unknown",
}
STRATEGY_SOURCES = {"legacy", "experiment", "ml", "replay", "counterfactual", "governance", "manual", "unknown"}
EVIDENCE_TYPES = {
    "experiment_summary",
    "replay_metrics",
    "replay_comparison",
    "counterfactual_estimate",
    "counterfactual_summary",
    "governance_status",
    "ml_registry",
    "legacy_baseline",
    "manual",
}
SIGNAL_DIRECTIONS = {"positive", "negative", "neutral"}
CONFIDENCE_LEVELS = {"insufficient", "low", "medium", "high"}
RISK_LEVELS = {"low", "medium", "high", "blocked"}
RECOMMENDATIONS = {
    "keep_baseline",
    "keep_shadow",
    "observe_more",
    "candidate_for_challenger",
    "risk_limited",
    "blocked_by_governance",
    "insufficient_evidence",
}


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _clean_dict(value: Any) -> dict[str, Any]:
    cleaned = to_jsonable(value if isinstance(value, dict) else {})
    return cleaned if isinstance(cleaned, dict) else {}


def _clean_list(value: Any) -> list[Any]:
    cleaned = to_jsonable(value if isinstance(value, list) else [])
    return cleaned if isinstance(cleaned, list) else []


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def _bool(value: Any, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on", "enabled", "pass", "passed"}


def _nullable_text(value: Any) -> str | None:
    if value is None or value == "":
        return None
    return str(value)


def _nullable_float(value: Any) -> float | None:
    return safe_float(value, None)


def _nullable_int(value: Any) -> int | None:
    return safe_int(value, None)


def _bounded(value: Any, default: float = 0.0) -> float:
    number = safe_float(value, default)
    if number is None:
        number = default
    return max(0.0, min(1.0, float(number)))


@dataclass
class StrategyProfile:
    strategy_id: str = ""
    strategy_type: str = "manual_or_unknown"
    name: str = ""
    description: str = ""
    source: str = "unknown"
    enabled: bool = True
    advisory_only: bool = True
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    raw_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["strategy_type"] = self.strategy_type if self.strategy_type in STRATEGY_TYPES else "manual_or_unknown"
        data["source"] = self.source if self.source in STRATEGY_SOURCES else "unknown"
        data["name"] = self.name or self.strategy_id
        data["enabled"] = _bool(self.enabled, True)
        data["advisory_only"] = _bool(self.advisory_only, True)
        data["raw_payload"] = _clean_dict(self.raw_payload)
        return _clean_dict(data)

    @classmethod
    def from_dict(cls, data: Any) -> "StrategyProfile":
        source = data.to_dict() if isinstance(data, StrategyProfile) else (data if isinstance(data, dict) else {})
        return cls(
            strategy_id=_text(source.get("strategy_id") or source.get("id")),
            strategy_type=_text(source.get("strategy_type") or "manual_or_unknown", "manual_or_unknown"),
            name=_text(source.get("name") or source.get("strategy_id") or source.get("id")),
            description=_text(source.get("description")),
            source=_text(source.get("source") or "unknown", "unknown"),
            enabled=_bool(source.get("enabled"), True),
            advisory_only=_bool(source.get("advisory_only"), True),
            created_at=_text(source.get("created_at") or utc_now_iso()),
            updated_at=_text(source.get("updated_at") or source.get("created_at") or utc_now_iso()),
            raw_payload=_clean_dict(source.get("raw_payload") or {}),
        )


@dataclass
class StrategyEvidence:
    evidence_id: str = ""
    strategy_id: str = ""
    evidence_type: str = "manual"
    sample_count: int = 0
    success_count: int | None = None
    avg_reward: float | None = None
    success_rate: float | None = None
    avg_platform_sc_abs_max: float | None = None
    quality_pass_rate: float | None = None
    replay_confidence: str | None = None
    counterfactual_confidence: str | None = None
    governance_status: str | None = None
    risk_flags: list[str] = field(default_factory=list)
    reason_codes: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now_iso)
    raw_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["evidence_type"] = self.evidence_type if self.evidence_type in EVIDENCE_TYPES else "manual"
        data["sample_count"] = max(0, int(safe_int(self.sample_count, 0) or 0))
        data["success_count"] = _nullable_int(self.success_count)
        data["avg_reward"] = _nullable_float(self.avg_reward)
        data["success_rate"] = _nullable_float(self.success_rate)
        data["avg_platform_sc_abs_max"] = _nullable_float(self.avg_platform_sc_abs_max)
        data["quality_pass_rate"] = _nullable_float(self.quality_pass_rate)
        data["risk_flags"] = [str(item) for item in _clean_list(self.risk_flags)]
        data["reason_codes"] = [str(item) for item in _clean_list(self.reason_codes)]
        data["raw_payload"] = _clean_dict(self.raw_payload)
        return _clean_dict(data)

    @classmethod
    def from_dict(cls, data: Any) -> "StrategyEvidence":
        source = data.to_dict() if isinstance(data, StrategyEvidence) else (data if isinstance(data, dict) else {})
        return cls(
            evidence_id=_text(source.get("evidence_id") or source.get("id")),
            strategy_id=_text(source.get("strategy_id")),
            evidence_type=_text(source.get("evidence_type") or "manual", "manual"),
            sample_count=max(0, int(safe_int(source.get("sample_count"), 0) or 0)),
            success_count=_nullable_int(source.get("success_count")),
            avg_reward=_nullable_float(source.get("avg_reward")),
            success_rate=_nullable_float(source.get("success_rate")),
            avg_platform_sc_abs_max=_nullable_float(source.get("avg_platform_sc_abs_max")),
            quality_pass_rate=_nullable_float(source.get("quality_pass_rate")),
            replay_confidence=_nullable_text(source.get("replay_confidence")),
            counterfactual_confidence=_nullable_text(source.get("counterfactual_confidence")),
            governance_status=_nullable_text(source.get("governance_status")),
            risk_flags=[str(item) for item in _clean_list(source.get("risk_flags") or [])],
            reason_codes=[str(item) for item in _clean_list(source.get("reason_codes") or [])],
            created_at=_text(source.get("created_at") or utc_now_iso()),
            raw_payload=_clean_dict(source.get("raw_payload") or {}),
        )


@dataclass
class StrategySignal:
    signal_id: str = ""
    strategy_id: str = ""
    signal_type: str = "stability_signal"
    value: float | str | bool | None = None
    weight: float = 1.0
    direction: str = "neutral"
    reason: str = ""
    created_at: str = field(default_factory=utc_now_iso)
    raw_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["value"] = to_jsonable(self.value)
        data["weight"] = float(safe_float(self.weight, 1.0) or 0.0)
        data["direction"] = self.direction if self.direction in SIGNAL_DIRECTIONS else "neutral"
        data["raw_payload"] = _clean_dict(self.raw_payload)
        return _clean_dict(data)

    @classmethod
    def from_dict(cls, data: Any) -> "StrategySignal":
        source = data.to_dict() if isinstance(data, StrategySignal) else (data if isinstance(data, dict) else {})
        return cls(
            signal_id=_text(source.get("signal_id") or source.get("id")),
            strategy_id=_text(source.get("strategy_id")),
            signal_type=_text(source.get("signal_type") or "stability_signal"),
            value=to_jsonable(source.get("value")),
            weight=float(safe_float(source.get("weight"), 1.0) or 0.0),
            direction=_text(source.get("direction") or "neutral", "neutral"),
            reason=_text(source.get("reason")),
            created_at=_text(source.get("created_at") or utc_now_iso()),
            raw_payload=_clean_dict(source.get("raw_payload") or {}),
        )


@dataclass
class StrategyScore:
    strategy_id: str = ""
    strategy_type: str = "manual_or_unknown"
    total_score: float = 0.0
    reward_score: float = 0.0
    success_score: float = 0.0
    sc_risk_score: float = 0.0
    quality_score: float = 0.0
    replay_score: float = 0.0
    counterfactual_score: float = 0.0
    governance_score: float = 0.0
    sample_size_score: float = 0.0
    confidence: str = "insufficient"
    risk_level: str = "medium"
    recommendation: str = "insufficient_evidence"
    evidence_count: int = 0
    sample_count: int = 0
    updated_at: str = field(default_factory=utc_now_iso)
    reason_codes: list[str] = field(default_factory=list)
    risk_flags: list[str] = field(default_factory=list)
    raw_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["strategy_type"] = self.strategy_type if self.strategy_type in STRATEGY_TYPES else "manual_or_unknown"
        for key in ("total_score", "reward_score", "success_score", "sc_risk_score", "quality_score", "replay_score", "counterfactual_score", "governance_score", "sample_size_score"):
            data[key] = _bounded(data.get(key), 0.0)
        data["confidence"] = self.confidence if self.confidence in CONFIDENCE_LEVELS else "insufficient"
        data["risk_level"] = self.risk_level if self.risk_level in RISK_LEVELS else "medium"
        data["recommendation"] = self.recommendation if self.recommendation in RECOMMENDATIONS else "insufficient_evidence"
        data["evidence_count"] = max(0, int(safe_int(self.evidence_count, 0) or 0))
        data["sample_count"] = max(0, int(safe_int(self.sample_count, 0) or 0))
        data["reason_codes"] = [str(item) for item in _clean_list(self.reason_codes)]
        data["risk_flags"] = [str(item) for item in _clean_list(self.risk_flags)]
        data["raw_payload"] = _clean_dict(self.raw_payload)
        return _clean_dict(data)

    @classmethod
    def from_dict(cls, data: Any) -> "StrategyScore":
        source = data.to_dict() if isinstance(data, StrategyScore) else (data if isinstance(data, dict) else {})
        return cls(
            strategy_id=_text(source.get("strategy_id")),
            strategy_type=_text(source.get("strategy_type") or "manual_or_unknown", "manual_or_unknown"),
            total_score=_bounded(source.get("total_score"), 0.0),
            reward_score=_bounded(source.get("reward_score"), 0.0),
            success_score=_bounded(source.get("success_score"), 0.0),
            sc_risk_score=_bounded(source.get("sc_risk_score"), 0.0),
            quality_score=_bounded(source.get("quality_score"), 0.0),
            replay_score=_bounded(source.get("replay_score"), 0.0),
            counterfactual_score=_bounded(source.get("counterfactual_score"), 0.0),
            governance_score=_bounded(source.get("governance_score"), 0.0),
            sample_size_score=_bounded(source.get("sample_size_score"), 0.0),
            confidence=_text(source.get("confidence") or "insufficient", "insufficient"),
            risk_level=_text(source.get("risk_level") or "medium", "medium"),
            recommendation=_text(source.get("recommendation") or "insufficient_evidence", "insufficient_evidence"),
            evidence_count=max(0, int(safe_int(source.get("evidence_count"), 0) or 0)),
            sample_count=max(0, int(safe_int(source.get("sample_count"), 0) or 0)),
            updated_at=_text(source.get("updated_at") or utc_now_iso()),
            reason_codes=[str(item) for item in _clean_list(source.get("reason_codes") or [])],
            risk_flags=[str(item) for item in _clean_list(source.get("risk_flags") or [])],
            raw_payload=_clean_dict(source.get("raw_payload") or {}),
        )


@dataclass
class StrategyScoreboard:
    scoreboard_id: str = ""
    generated_at: str = field(default_factory=utc_now_iso)
    profiles: list[StrategyProfile] = field(default_factory=list)
    scores: list[StrategyScore] = field(default_factory=list)
    signals: list[StrategySignal] = field(default_factory=list)
    evidence_summary: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    raw_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["profiles"] = [StrategyProfile.from_dict(item).to_dict() for item in self.profiles]
        data["scores"] = [StrategyScore.from_dict(item).to_dict() for item in self.scores]
        data["signals"] = [StrategySignal.from_dict(item).to_dict() for item in self.signals]
        data["evidence_summary"] = _clean_dict(self.evidence_summary)
        data["warnings"] = [str(item) for item in _clean_list(self.warnings)]
        data["raw_payload"] = _clean_dict(self.raw_payload)
        return _clean_dict(data)

    @classmethod
    def from_dict(cls, data: Any) -> "StrategyScoreboard":
        source = data.to_dict() if isinstance(data, StrategyScoreboard) else (data if isinstance(data, dict) else {})
        return cls(
            scoreboard_id=_text(source.get("scoreboard_id") or source.get("id")),
            generated_at=_text(source.get("generated_at") or utc_now_iso()),
            profiles=[StrategyProfile.from_dict(item) for item in _clean_list(source.get("profiles") or [])],
            scores=[StrategyScore.from_dict(item) for item in _clean_list(source.get("scores") or [])],
            signals=[StrategySignal.from_dict(item) for item in _clean_list(source.get("signals") or [])],
            evidence_summary=_clean_dict(source.get("evidence_summary") or {}),
            warnings=[str(item) for item in _clean_list(source.get("warnings") or [])],
            raw_payload=_clean_dict(source.get("raw_payload") or {}),
        )
