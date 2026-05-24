from __future__ import annotations

import math
from datetime import datetime

from .models import ResearchInsight


class InsightScorer:
    def score_all(self, insights: list[ResearchInsight], *, current_round: int = 0) -> list[ResearchInsight]:
        return [self.score(insight, current_round=current_round) for insight in insights]

    def score(self, insight: ResearchInsight, *, current_round: int = 0) -> ResearchInsight:
        support = max(0, int(insight.support_count))
        contradiction = max(0, int(insight.contradiction_count))
        newest_round = max(insight.source_rounds or [0])
        age_rounds = max(0, int(current_round or newest_round) - newest_round)

        support_score = min(1.0, math.log1p(support) / math.log1p(20))
        contradiction_rate = contradiction / max(support + contradiction, 1)
        freshness_score = max(0.05, 1.0 - age_rounds / 150.0)
        decay_score = self._decay_score(insight, age_rounds)

        confidence = (
            0.12
            + support_score * 0.42
            + freshness_score * 0.22
            + decay_score * 0.20
            - contradiction_rate * 0.46
        )
        insight.support_count = support
        insight.contradiction_count = contradiction
        insight.freshness_score = _clamp(freshness_score)
        insight.decay_score = _clamp(decay_score)
        insight.confidence = _clamp(confidence)
        return insight

    def _decay_score(self, insight: ResearchInsight, age_rounds: int) -> float:
        round_decay = max(0.0, 1.0 - age_rounds / 300.0)
        updated = _parse_time(insight.updated_at)
        if updated is None:
            return round_decay
        age_days = max(0.0, (datetime.now() - updated).total_seconds() / 86400.0)
        day_decay = max(0.0, 1.0 - age_days / 90.0)
        return min(round_decay, day_decay)


def _parse_time(text: str) -> datetime | None:
    if not text:
        return None
    try:
        return datetime.fromisoformat(text[:19])
    except ValueError:
        return None


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))
