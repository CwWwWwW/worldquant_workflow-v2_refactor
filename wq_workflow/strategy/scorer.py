from __future__ import annotations

import uuid
from typing import Any

from wq_workflow.data.json_utils import safe_float

from .schema import StrategyEvidence, StrategyProfile, StrategyScore, StrategySignal, utc_now_iso


class StrategyScorer:
    def __init__(self, config: Any | None = None, logger: Any | None = None) -> None:
        self.config = config
        self.logger = logger

    def score_strategy(self, profile: StrategyProfile, evidence: list[StrategyEvidence]) -> StrategyScore:
        profile = StrategyProfile.from_dict(profile)
        rows = [StrategyEvidence.from_dict(item) for item in evidence if StrategyEvidence.from_dict(item).strategy_id == profile.strategy_id]
        evidence_count = len(rows)
        sample_count = sum(max(0, int(item.sample_count or 0)) for item in rows)
        risk_flags = list(dict.fromkeys(flag for item in rows for flag in (item.risk_flags or [])))
        reason_codes = list(dict.fromkeys(code for item in rows for code in (item.reason_codes or [])))
        avg_reward = self._weighted_average(rows, "avg_reward")
        success_rate = self._weighted_average(rows, "success_rate")
        avg_sc = self._weighted_average(rows, "avg_platform_sc_abs_max")
        quality_rate = self._weighted_average(rows, "quality_pass_rate")
        replay_confidence = self._max_confidence([item.replay_confidence for item in rows])
        counterfactual_confidence = self._max_confidence([item.counterfactual_confidence for item in rows])
        reward_score = self._reward_score(avg_reward)
        success_score = self._rate_score(success_rate, default=0.40)
        sc_risk_score = self._sc_score(avg_sc)
        quality_score = self._rate_score(quality_rate, default=0.50)
        replay_score = self._confidence_score(replay_confidence) if any(item.evidence_type.startswith("replay") for item in rows) else 0.0
        counterfactual_score = min(0.75, self._confidence_score(counterfactual_confidence)) if any(item.evidence_type.startswith("counterfactual") for item in rows) else 0.0
        governance_score = self._governance_score(rows)
        sample_size_score = self._sample_size_score(sample_count)
        confidence = self.confidence_from_evidence(evidence_count, sample_count, replay_confidence, counterfactual_confidence)
        risk_level = self.risk_level_from_evidence(rows)
        total_score = (
            reward_score * 0.20
            + success_score * 0.18
            + sc_risk_score * 0.17
            + quality_score * 0.12
            + replay_score * 0.10
            + counterfactual_score * 0.08
            + governance_score * 0.10
            + sample_size_score * 0.05
        )
        score = StrategyScore(
            strategy_id=profile.strategy_id,
            strategy_type=profile.strategy_type,
            total_score=max(0.0, min(1.0, total_score)),
            reward_score=reward_score,
            success_score=success_score,
            sc_risk_score=sc_risk_score,
            quality_score=quality_score,
            replay_score=replay_score,
            counterfactual_score=counterfactual_score,
            governance_score=governance_score,
            sample_size_score=sample_size_score,
            confidence=confidence,
            risk_level=risk_level,
            evidence_count=evidence_count,
            sample_count=sample_count,
            updated_at=utc_now_iso(),
            reason_codes=reason_codes,
            risk_flags=risk_flags,
            raw_payload={"advisory_only": True, "counterfactual_is_estimate": profile.strategy_type == "counterfactual_supported_policy"},
        )
        score.recommendation = self.recommendation_from_score(score)
        return score

    def build_signals(self, profile: StrategyProfile, evidence: list[StrategyEvidence]) -> list[StrategySignal]:
        score = self.score_strategy(profile, evidence)
        fields = [
            ("reward_signal", score.reward_score, "positive", "normalized average reward evidence"),
            ("success_signal", score.success_score, "positive", "success-rate evidence"),
            ("sc_risk_signal", score.sc_risk_score, "negative" if score.sc_risk_score < 0.5 else "positive", "platform SC risk evidence"),
            ("quality_signal", score.quality_score, "positive", "quality-pass evidence"),
            ("replay_signal", score.replay_score, "positive" if score.replay_score else "neutral", "offline replay support"),
            ("counterfactual_signal", score.counterfactual_score, "neutral", "counterfactual estimate support; not actual outcome"),
            ("governance_signal", score.governance_score, "negative" if score.risk_level == "blocked" else "positive", "governance risk signal"),
            ("sample_size_signal", score.sample_size_score, "positive" if score.sample_size_score >= 0.5 else "neutral", "sample-size confidence"),
        ]
        now = utc_now_iso()
        return [StrategySignal(signal_id=f"sig:{profile.strategy_id}:{name}:{uuid.uuid4().hex[:8]}", strategy_id=profile.strategy_id, signal_type=name, value=value, weight=1.0, direction=direction, reason=reason, created_at=now) for name, value, direction, reason in fields]

    def confidence_from_evidence(self, evidence_count: int, sample_count: int, replay_confidence: str | None = None, counterfactual_confidence: str | None = None) -> str:
        if evidence_count <= 0 or sample_count < int(getattr(self.config, "strategy_score_min_samples", 30) or 30):
            return "insufficient"
        if sample_count < int(getattr(self.config, "strategy_score_medium_samples", 100) or 100):
            return "low"
        if sample_count < int(getattr(self.config, "strategy_score_high_samples", 500) or 500):
            return "medium"
        return "high"

    def risk_level_from_evidence(self, evidence: list[StrategyEvidence]) -> str:
        flags = {flag for item in evidence for flag in (item.risk_flags or [])}
        statuses = {str(item.governance_status or "").lower() for item in evidence}
        if flags & {"governance_blocked", "blocked_by_governance"} or statuses & {"blocked", "fail", "failed", "invalid"}:
            return "blocked"
        threshold = float(getattr(self.config, "strategy_high_sc_abs_max_threshold", 0.70) or 0.70)
        if flags & {"high_risk_estimate", "counterfactual_high_risk", "high_sc_risk"}:
            return "high"
        for item in evidence:
            value = safe_float(item.avg_platform_sc_abs_max, None)
            if value is not None and abs(float(value)) >= threshold:
                return "high"
        if flags:
            return "medium"
        return "low"

    def recommendation_from_score(self, score: StrategyScore) -> str:
        if score.strategy_type == "legacy_baseline":
            return "keep_baseline"
        if score.risk_level == "blocked":
            return "blocked_by_governance"
        if score.risk_level == "high":
            return "risk_limited"
        if score.strategy_type == "random_exploration":
            return "keep_shadow" if score.confidence in {"insufficient", "low"} else "observe_more"
        if score.strategy_type == "counterfactual_supported_policy":
            if "high_risk_estimate" in set(score.risk_flags or []):
                return "risk_limited"
            if score.confidence in {"insufficient", "low"}:
                return "insufficient_evidence"
            return "observe_more"
        if score.confidence == "insufficient":
            return "observe_more" if score.strategy_type == "experiment_budget" else "insufficient_evidence"
        if score.confidence == "low":
            return "observe_more"
        if score.total_score >= 0.65 and score.risk_level == "low":
            return "candidate_for_challenger"
        if score.total_score >= 0.50:
            return "observe_more"
        return "keep_shadow"

    def _weighted_average(self, evidence: list[StrategyEvidence], attr: str) -> float | None:
        values: list[float] = []
        weights: list[int] = []
        for item in evidence:
            value = safe_float(getattr(item, attr, None), None)
            if value is None:
                continue
            values.append(float(value))
            weights.append(max(1, int(item.sample_count or 0)))
        if not values:
            return None
        total = sum(weights) or len(weights)
        return sum(v * w for v, w in zip(values, weights)) / total

    def _reward_score(self, value: float | None) -> float:
        if value is None:
            return 0.50
        return max(0.0, min(1.0, 0.5 + float(value) / 2.0))

    def _rate_score(self, value: float | None, default: float = 0.5) -> float:
        if value is None:
            return default
        return max(0.0, min(1.0, float(value)))

    def _sc_score(self, value: float | None) -> float:
        if value is None:
            return 0.70
        threshold = float(getattr(self.config, "strategy_high_sc_abs_max_threshold", 0.70) or 0.70)
        return max(0.0, min(1.0, 1.0 - abs(float(value)) / max(threshold, 0.01)))

    def _confidence_score(self, value: str | None) -> float:
        return {"insufficient": 0.0, "low": 0.35, "medium": 0.70, "high": 1.0}.get(str(value or "").lower(), 0.0)

    def _max_confidence(self, values: list[str | None]) -> str | None:
        order = {"insufficient": 0, "low": 1, "medium": 2, "high": 3}
        best = None
        best_score = -1
        for value in values:
            key = str(value or "").lower()
            if order.get(key, -1) > best_score:
                best = key
                best_score = order.get(key, -1)
        return best

    def _sample_size_score(self, sample_count: int) -> float:
        high = int(getattr(self.config, "strategy_score_high_samples", 500) or 500)
        return max(0.0, min(1.0, sample_count / max(high, 1)))

    def _governance_score(self, evidence: list[StrategyEvidence]) -> float:
        statuses = {str(item.governance_status or "").lower() for item in evidence if item.governance_status}
        flags = {flag for item in evidence for flag in (item.risk_flags or [])}
        if statuses & {"blocked", "fail", "failed", "invalid"} or "governance_blocked" in flags:
            return 0.0
        if statuses:
            return 0.80
        return 0.60
