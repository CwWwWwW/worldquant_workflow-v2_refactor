from __future__ import annotations

import uuid
from typing import Any

from .portfolio_schema import StrategyTransition, utc_now_iso
from .schema import StrategyScore

_CONFIDENCE_ORDER = {"insufficient": 0, "low": 1, "medium": 2, "high": 3}
_LOW_MEDIUM_RISK = {"low", "medium"}
_BLOCKED_GOVERNANCE = {"blocked", "block", "veto", "vetoed", "disabled", "deny", "denied"}
_HIGH_SC_FLAGS = {"high_sc_risk", "high_risk_estimate"}


class StrategyTransitionRules:
    def __init__(self, config: Any | None = None, logger: Any | None = None) -> None:
        self.config = config
        self.logger = logger

    def recommend_state(self, score: StrategyScore, current_state: str | None = None) -> StrategyTransition:
        item = StrategyScore.from_dict(score)
        from_state = self.normalize_state(current_state or self.default_state_for_strategy(item.strategy_id, item.strategy_type))
        reason_codes = list(dict.fromkeys([str(x) for x in (item.reason_codes or [])]))
        risk_flags = list(dict.fromkeys([str(x) for x in (item.risk_flags or [])]))
        recommendation = "keep_current"
        to_state = from_state
        allowed = True

        if item.strategy_id == self.default_champion:
            from_state = "champion"
            to_state = "champion"
            recommendation = "keep_baseline"
            reason_codes.append("default_champion_legacy_baseline")
        elif self.is_blocked(item):
            to_state = "disabled"
            recommendation = "blocked_by_governance"
            allowed = False
            reason_codes.append("blocked_by_governance")
        elif item.risk_level == "high":
            to_state = "shadow"
            recommendation = "demote_to_shadow" if from_state in {"challenger", "limited_active"} else "risk_limited"
            reason_codes.append("risk_level_high")
        elif item.strategy_id == "random_exploration":
            to_state = "shadow"
            recommendation = "keep_shadow"
            reason_codes.append("random_exploration_observe_only")
        elif not self.has_sufficient_evidence(item):
            to_state = "shadow"
            recommendation = "insufficient_evidence"
            reason_codes.append("insufficient_evidence")
        elif self.can_recommend_limited_active(item):
            if from_state == "limited_active" and bool(getattr(self.config, "strategy_allow_auto_champion_promotion", False)) is False:
                to_state = "limited_active"
                recommendation = "future_candidate_for_champion"
                reason_codes.append("champion_promotion_requires_future_phase")
            else:
                to_state = "limited_active"
                recommendation = "recommend_limited_active"
                reason_codes.append("limited_active_candidate")
        elif self.can_promote_to_challenger(item):
            to_state = "challenger"
            recommendation = "promote_to_challenger"
            reason_codes.append("challenger_candidate")
        else:
            to_state = "shadow"
            recommendation = "observe_more" if item.confidence == "low" else "insufficient_evidence"
            reason_codes.append("observe_more")

        if to_state == "champion" and item.strategy_id != self.default_champion:
            to_state = "limited_active"
            recommendation = "future_candidate_for_champion"
            reason_codes.append("auto_champion_promotion_blocked")

        return StrategyTransition(
            transition_id=f"strategy_transition:{uuid.uuid4().hex}",
            strategy_id=item.strategy_id,
            from_state=from_state,
            to_state=to_state,
            recommendation=recommendation,
            allowed=allowed,
            auto_apply_allowed=False,
            confidence=item.confidence,
            reason_codes=list(dict.fromkeys(reason_codes))[-100:],
            risk_flags=risk_flags[-100:],
            created_at=utc_now_iso(),
            raw_payload={"advisory_only": True, "score": item.to_dict()},
        )

    def can_promote_to_challenger(self, score: StrategyScore) -> bool:
        item = StrategyScore.from_dict(score)
        return (
            self.has_sufficient_evidence(item)
            and _CONFIDENCE_ORDER.get(item.confidence, 0) >= _CONFIDENCE_ORDER.get(str(getattr(self.config, "strategy_challenger_min_confidence", "medium") or "medium"), 2)
            and item.risk_level in _LOW_MEDIUM_RISK
            and not self.is_blocked(item)
        )

    def can_recommend_limited_active(self, score: StrategyScore) -> bool:
        item = StrategyScore.from_dict(score)
        min_samples = max(1, int(getattr(self.config, "strategy_limited_active_min_samples", 500) or 500))
        min_conf = str(getattr(self.config, "strategy_limited_active_min_confidence", "high") or "high")
        return (
            item.sample_count >= min_samples
            and _CONFIDENCE_ORDER.get(item.confidence, 0) >= _CONFIDENCE_ORDER.get(min_conf, 3)
            and item.risk_level == "low"
            and not self.has_high_sc_risk(item)
            and not self.is_blocked(item)
        )

    def is_blocked(self, score: StrategyScore) -> bool:
        item = StrategyScore.from_dict(score)
        raw = item.raw_payload if isinstance(item.raw_payload, dict) else {}
        governance_status = str(raw.get("governance_status") or raw.get("governance_decision") or "").strip().lower()
        flags = {str(flag).strip().lower() for flag in item.risk_flags or []}
        reasons = {str(reason).strip().lower() for reason in item.reason_codes or []}
        return item.risk_level == "blocked" or governance_status in _BLOCKED_GOVERNANCE or bool(flags & _BLOCKED_GOVERNANCE) or bool(reasons & _BLOCKED_GOVERNANCE)

    def has_high_sc_risk(self, score: StrategyScore) -> bool:
        item = StrategyScore.from_dict(score)
        if not bool(getattr(self.config, "strategy_block_high_sc_risk", True)):
            return False
        flags = {str(flag).strip().lower() for flag in item.risk_flags or []}
        return bool(flags & _HIGH_SC_FLAGS)

    def has_sufficient_evidence(self, score: StrategyScore) -> bool:
        item = StrategyScore.from_dict(score)
        min_samples = max(1, int(getattr(self.config, "strategy_challenger_min_samples", 100) or 100))
        return item.sample_count >= min_samples and item.confidence not in {"insufficient", "low"}

    def default_state_for_strategy(self, strategy_id: str, strategy_type: str | None = None) -> str:
        sid = str(strategy_id or "")
        stype = str(strategy_type or "")
        if sid == self.default_champion or stype == "legacy_baseline":
            return "champion"
        if sid == "random_exploration" or stype == "random_exploration":
            return "shadow"
        return "shadow"

    def normalize_state(self, state: str | None) -> str:
        text = str(state or "shadow").strip().lower()
        return text if text in {"disabled", "shadow", "challenger", "limited_active", "champion"} else "shadow"

    @property
    def default_champion(self) -> str:
        return str(getattr(self.config, "strategy_default_champion", "legacy_baseline") or "legacy_baseline")


StrategyTransitionRule = StrategyTransitionRules
