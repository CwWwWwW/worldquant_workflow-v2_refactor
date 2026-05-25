from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from wq_workflow.data.json_utils import safe_float, safe_int, to_jsonable

STRATEGY_PORTFOLIO_STATES = {"disabled", "shadow", "challenger", "limited_active", "champion"}
STRATEGY_PORTFOLIO_ROLES = {"baseline", "challenger", "observer", "blocked", "unknown"}
STRATEGY_TRANSITION_RECOMMENDATIONS = {
    "keep_current",
    "keep_baseline",
    "keep_shadow",
    "promote_to_shadow",
    "promote_to_challenger",
    "recommend_limited_active",
    "future_candidate_for_champion",
    "demote_to_shadow",
    "recommend_disabled",
    "blocked_by_governance",
    "insufficient_evidence",
    "observe_more",
    "risk_limited",
}
CONFIDENCE_LEVELS = {"insufficient", "low", "medium", "high"}
RISK_LEVELS = {"low", "medium", "high", "blocked"}


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


def _state(value: Any, default: str = "shadow") -> str:
    text = _text(value or default, default).strip().lower()
    return text if text in STRATEGY_PORTFOLIO_STATES else default


def _role(value: Any, default: str = "unknown") -> str:
    text = _text(value or default, default).strip().lower()
    return text if text in STRATEGY_PORTFOLIO_ROLES else default


def _confidence(value: Any, default: str = "insufficient") -> str:
    text = _text(value or default, default).strip().lower()
    return text if text in CONFIDENCE_LEVELS else default


def _risk(value: Any, default: str = "medium") -> str:
    text = _text(value or default, default).strip().lower()
    return text if text in RISK_LEVELS else default


def _recommendation(value: Any, default: str = "keep_current") -> str:
    text = _text(value or default, default).strip().lower()
    return text if text in STRATEGY_TRANSITION_RECOMMENDATIONS else default


@dataclass
class StrategyState:
    strategy_id: str = ""
    strategy_type: str = "manual_or_unknown"
    current_state: str = "shadow"
    recommended_state: str = "shadow"
    current_role: str = "unknown"
    confidence: str = "insufficient"
    risk_level: str = "medium"
    score: float = 0.0
    sample_count: int = 0
    evidence_count: int = 0
    governance_status: str | None = None
    reason_codes: list[str] = field(default_factory=list)
    risk_flags: list[str] = field(default_factory=list)
    updated_at: str = field(default_factory=utc_now_iso)
    raw_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["current_state"] = _state(self.current_state)
        data["recommended_state"] = _state(self.recommended_state)
        data["current_role"] = _role(self.current_role)
        data["confidence"] = _confidence(self.confidence)
        data["risk_level"] = _risk(self.risk_level)
        data["score"] = float(safe_float(self.score, 0.0) or 0.0)
        data["sample_count"] = max(0, int(safe_int(self.sample_count, 0) or 0))
        data["evidence_count"] = max(0, int(safe_int(self.evidence_count, 0) or 0))
        data["governance_status"] = _nullable_text(self.governance_status)
        data["reason_codes"] = [str(item) for item in _clean_list(self.reason_codes)]
        data["risk_flags"] = [str(item) for item in _clean_list(self.risk_flags)]
        data["raw_payload"] = _clean_dict(self.raw_payload)
        return _clean_dict(data)

    @classmethod
    def from_dict(cls, data: Any) -> "StrategyState":
        source = data.to_dict() if isinstance(data, StrategyState) else (data if isinstance(data, dict) else {})
        return cls(
            strategy_id=_text(source.get("strategy_id")),
            strategy_type=_text(source.get("strategy_type") or "manual_or_unknown", "manual_or_unknown"),
            current_state=_state(source.get("current_state")),
            recommended_state=_state(source.get("recommended_state")),
            current_role=_role(source.get("current_role")),
            confidence=_confidence(source.get("confidence")),
            risk_level=_risk(source.get("risk_level")),
            score=float(safe_float(source.get("score"), 0.0) or 0.0),
            sample_count=max(0, int(safe_int(source.get("sample_count"), 0) or 0)),
            evidence_count=max(0, int(safe_int(source.get("evidence_count"), 0) or 0)),
            governance_status=_nullable_text(source.get("governance_status")),
            reason_codes=[str(item) for item in _clean_list(source.get("reason_codes") or [])],
            risk_flags=[str(item) for item in _clean_list(source.get("risk_flags") or [])],
            updated_at=_text(source.get("updated_at") or utc_now_iso()),
            raw_payload=_clean_dict(source.get("raw_payload") or {}),
        )


@dataclass
class StrategyTransition:
    transition_id: str = ""
    strategy_id: str = ""
    from_state: str = "shadow"
    to_state: str = "shadow"
    recommendation: str = "keep_current"
    allowed: bool = True
    auto_apply_allowed: bool = False
    confidence: str = "insufficient"
    reason_codes: list[str] = field(default_factory=list)
    risk_flags: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now_iso)
    raw_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["from_state"] = _state(self.from_state)
        data["to_state"] = _state(self.to_state)
        data["recommendation"] = _recommendation(self.recommendation)
        data["allowed"] = _bool(self.allowed, True)
        data["auto_apply_allowed"] = False
        data["confidence"] = _confidence(self.confidence)
        data["reason_codes"] = [str(item) for item in _clean_list(self.reason_codes)]
        data["risk_flags"] = [str(item) for item in _clean_list(self.risk_flags)]
        data["raw_payload"] = _clean_dict(self.raw_payload)
        return _clean_dict(data)

    @classmethod
    def from_dict(cls, data: Any) -> "StrategyTransition":
        source = data.to_dict() if isinstance(data, StrategyTransition) else (data if isinstance(data, dict) else {})
        return cls(
            transition_id=_text(source.get("transition_id") or source.get("id")),
            strategy_id=_text(source.get("strategy_id")),
            from_state=_state(source.get("from_state")),
            to_state=_state(source.get("to_state")),
            recommendation=_recommendation(source.get("recommendation")),
            allowed=_bool(source.get("allowed"), True),
            auto_apply_allowed=False,
            confidence=_confidence(source.get("confidence")),
            reason_codes=[str(item) for item in _clean_list(source.get("reason_codes") or [])],
            risk_flags=[str(item) for item in _clean_list(source.get("risk_flags") or [])],
            created_at=_text(source.get("created_at") or utc_now_iso()),
            raw_payload=_clean_dict(source.get("raw_payload") or {}),
        )


@dataclass
class StrategyPortfolio:
    portfolio_id: str = ""
    generated_at: str = field(default_factory=utc_now_iso)
    champion_strategy_id: str = "legacy_baseline"
    states: list[StrategyState] = field(default_factory=list)
    transitions: list[StrategyTransition] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    raw_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["states"] = [StrategyState.from_dict(item).to_dict() for item in self.states]
        data["transitions"] = [StrategyTransition.from_dict(item).to_dict() for item in self.transitions]
        data["warnings"] = [str(item) for item in _clean_list(self.warnings)]
        data["raw_payload"] = _clean_dict(self.raw_payload)
        return _clean_dict(data)

    @classmethod
    def from_dict(cls, data: Any) -> "StrategyPortfolio":
        source = data.to_dict() if isinstance(data, StrategyPortfolio) else (data if isinstance(data, dict) else {})
        return cls(
            portfolio_id=_text(source.get("portfolio_id") or source.get("id")),
            generated_at=_text(source.get("generated_at") or utc_now_iso()),
            champion_strategy_id=_text(source.get("champion_strategy_id") or "legacy_baseline", "legacy_baseline"),
            states=[StrategyState.from_dict(item) for item in _clean_list(source.get("states") or [])],
            transitions=[StrategyTransition.from_dict(item) for item in _clean_list(source.get("transitions") or [])],
            warnings=[str(item) for item in _clean_list(source.get("warnings") or [])],
            raw_payload=_clean_dict(source.get("raw_payload") or {}),
        )


@dataclass
class StrategyPortfolioReport:
    report_id: str = ""
    generated_at: str = field(default_factory=utc_now_iso)
    mode: str = "advisory"
    champion_strategy_id: str = "legacy_baseline"
    strategy_states: list[StrategyState] = field(default_factory=list)
    recommended_transitions: list[StrategyTransition] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    raw_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["mode"] = str(self.mode or "advisory")
        data["strategy_states"] = [StrategyState.from_dict(item).to_dict() for item in self.strategy_states]
        data["recommended_transitions"] = [StrategyTransition.from_dict(item).to_dict() for item in self.recommended_transitions]
        data["warnings"] = [str(item) for item in _clean_list(self.warnings)]
        data["raw_payload"] = _clean_dict(self.raw_payload)
        return _clean_dict(data)

    @classmethod
    def from_dict(cls, data: Any) -> "StrategyPortfolioReport":
        source = data.to_dict() if isinstance(data, StrategyPortfolioReport) else (data if isinstance(data, dict) else {})
        return cls(
            report_id=_text(source.get("report_id") or source.get("id")),
            generated_at=_text(source.get("generated_at") or utc_now_iso()),
            mode=_text(source.get("mode") or "advisory", "advisory"),
            champion_strategy_id=_text(source.get("champion_strategy_id") or "legacy_baseline", "legacy_baseline"),
            strategy_states=[StrategyState.from_dict(item) for item in _clean_list(source.get("strategy_states") or source.get("states") or [])],
            recommended_transitions=[StrategyTransition.from_dict(item) for item in _clean_list(source.get("recommended_transitions") or source.get("transitions") or [])],
            warnings=[str(item) for item in _clean_list(source.get("warnings") or [])],
            raw_payload=_clean_dict(source.get("raw_payload") or {}),
        )
