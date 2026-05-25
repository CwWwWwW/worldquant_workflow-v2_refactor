from __future__ import annotations

import uuid
from typing import Any

from .portfolio_schema import StrategyPortfolio, StrategyState, StrategyTransition, utc_now_iso
from .schema import StrategyScore
from .transition_rules import StrategyTransitionRules


class ChampionChallengerPolicy:
    def __init__(self, config: Any | None = None, logger: Any | None = None, rules: StrategyTransitionRules | None = None) -> None:
        self.config = config
        self.logger = logger
        self.rules = rules or StrategyTransitionRules(config=config, logger=logger)

    def evaluate_scores(self, scores: list[StrategyScore], current_states: dict | None = None) -> StrategyPortfolio:
        current_states = current_states if isinstance(current_states, dict) else {}
        normalized = [StrategyScore.from_dict(item) for item in scores or []]
        champion = self.choose_champion(normalized)
        transitions: list[StrategyTransition] = []
        states: list[StrategyState] = []
        for score in normalized:
            current = current_states.get(score.strategy_id)
            if isinstance(current, dict):
                current = current.get("current_state") or current.get("recommended_state")
            transition = self.rules.recommend_state(score, current_state=current)
            transitions.append(transition)
            states.append(self.build_state(score, transition))
        if champion and not any(state.strategy_id == champion for state in states):
            baseline = StrategyScore(strategy_id=champion, strategy_type="legacy_baseline", total_score=0.5, confidence="medium", risk_level="low", sample_count=0, recommendation="keep_baseline")
            transition = self.rules.recommend_state(baseline, current_state="champion")
            transitions.insert(0, transition)
            states.insert(0, self.build_state(baseline, transition))
        warnings = self.generate_warnings(states, transitions)
        return StrategyPortfolio(
            portfolio_id=f"strategy_portfolio:{uuid.uuid4().hex}",
            generated_at=utc_now_iso(),
            champion_strategy_id=champion,
            states=states,
            transitions=transitions,
            warnings=warnings,
            raw_payload={"mode": getattr(self.config, "strategy_portfolio_mode", "advisory"), "advisory_only": True},
        )

    def build_state(self, score: StrategyScore, transition: StrategyTransition) -> StrategyState:
        item = StrategyScore.from_dict(score)
        trans = StrategyTransition.from_dict(transition)
        role = "unknown"
        if trans.to_state == "champion" or item.strategy_id == self.choose_champion([item]):
            role = "baseline"
        elif trans.to_state == "disabled":
            role = "blocked"
        elif trans.to_state in {"challenger", "limited_active"}:
            role = "challenger"
        elif trans.to_state == "shadow":
            role = "observer"
        raw = item.raw_payload if isinstance(item.raw_payload, dict) else {}
        governance_status = raw.get("governance_status") or raw.get("governance_decision")
        return StrategyState(
            strategy_id=item.strategy_id,
            strategy_type=item.strategy_type,
            current_state=trans.from_state,
            recommended_state=trans.to_state,
            current_role=role,
            confidence=item.confidence,
            risk_level=item.risk_level,
            score=item.total_score,
            sample_count=item.sample_count,
            evidence_count=item.evidence_count,
            governance_status=governance_status,
            reason_codes=list(dict.fromkeys((item.reason_codes or []) + (trans.reason_codes or [])))[-100:],
            risk_flags=list(dict.fromkeys((item.risk_flags or []) + (trans.risk_flags or [])))[-100:],
            updated_at=utc_now_iso(),
            raw_payload={"advisory_only": True, "score": item.to_dict(), "transition_id": trans.transition_id},
        )

    def choose_champion(self, scores: list[StrategyScore]) -> str:
        return str(getattr(self.config, "strategy_default_champion", "legacy_baseline") or "legacy_baseline")

    def generate_warnings(self, states: list[StrategyState], transitions: list[StrategyTransition]) -> list[str]:
        warnings: list[str] = []
        if not any(state.strategy_id == self.choose_champion([]) and state.recommended_state == "champion" for state in states):
            warnings.append("default_champion_state_synthesized_or_missing")
        if any(state.risk_level == "blocked" or state.recommended_state == "disabled" for state in states):
            warnings.append("one_or_more_strategies_blocked")
        if any(transition.auto_apply_allowed for transition in transitions):
            warnings.append("auto_apply_forced_false")
            for transition in transitions:
                transition.auto_apply_allowed = False
        if any(state.confidence in {"insufficient", "low"} for state in states):
            warnings.append("one_or_more_strategies_need_more_evidence")
        return list(dict.fromkeys(warnings))[-100:]
