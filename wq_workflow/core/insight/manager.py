from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from ...paths import INSIGHT_STATE_FILE, RESEARCH_INSIGHTS_FILE, ROOT
from ...safe_io import atomic_write_json, safe_read_json
from .cluster import InsightClusterer
from .extractor import InsightExtractor
from .injector import InsightInjector
from .models import ResearchInsight
from .scorer import InsightScorer
from .summarizer import InsightSummarizer


class InsightManager:
    def __init__(
        self,
        *,
        root: Path | str | None = None,
        insights_file: Path | str | None = None,
        state_file: Path | str | None = None,
    ) -> None:
        self.root = Path(root) if root is not None else ROOT
        self.insights_file = Path(insights_file) if insights_file is not None else RESEARCH_INSIGHTS_FILE
        self.state_file = Path(state_file) if state_file is not None else INSIGHT_STATE_FILE
        if root is not None and insights_file is None:
            self.insights_file = self.root / "memory" / "insights" / "research_insights.json"
        if root is not None and state_file is None:
            self.state_file = self.root / "memory" / "insights" / "insight_state.json"
        self.extractor = InsightExtractor(self.root)
        self.clusterer = InsightClusterer()
        self.summarizer = InsightSummarizer()
        self.scorer = InsightScorer()
        self.injector = InsightInjector()

    def load_insights(self) -> list[ResearchInsight]:
        data = safe_read_json(self.insights_file, [])
        if isinstance(data, dict):
            data = data.get("insights", [])
        if not isinstance(data, list):
            return []
        result: list[ResearchInsight] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            insight = ResearchInsight.from_dict(item)
            if insight.summary:
                if not insight.id:
                    insight.id = _insight_id(insight.type, insight.summary, insight.related_operators)
                result.append(insight)
        return result

    def save_insights(self, insights: list[ResearchInsight]) -> None:
        self.insights_file.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(self.insights_file, [insight.to_dict() for insight in insights])

    def top_k_for_context(self, context: dict[str, Any], *, k: int = 5) -> list[ResearchInsight]:
        try:
            insights = self.load_insights()
        except Exception as exc:
            logging.warning("Research insight load skipped: %s", exc)
            return []
        return self.injector.top_k(insights, context, k=k)

    def format_for_context(self, context: dict[str, Any], *, k: int = 5, max_chars: int = 900) -> str:
        return self.injector.format_for_prompt(self.top_k_for_context(context, k=k), max_chars=max_chars)

    async def distill_if_due(
        self,
        client: Any | None = None,
        *,
        interval: int = 50,
        min_samples: int = 20,
        max_prompt_clusters: int = 16,
        force: bool = False,
    ) -> list[ResearchInsight]:
        samples = self.extractor.extract_all()
        sample_count = len(samples)
        state = self._load_state()
        last_count = _int(state.get("last_sample_count"))
        if not force:
            if sample_count < max(1, int(min_samples)):
                return []
            if sample_count - last_count < max(1, int(interval)):
                return []
        clusters = self.clusterer.cluster(samples)
        if not clusters:
            self._save_state(sample_count, generated=0)
            return []
        generated = await self.summarizer.summarize(clusters, client=client, max_clusters=max_prompt_clusters)
        if not generated:
            self._save_state(sample_count, generated=0)
            return []
        current_round = max((sample.source_round for sample in samples), default=sample_count)
        scored = self.scorer.score_all(generated, current_round=current_round)
        merged = self.merge_insights(self.load_insights(), scored)
        pruned = self.prune_stale(merged)
        self.save_insights(pruned)
        self._save_state(sample_count, generated=len(scored))
        return scored

    def merge_insights(
        self,
        existing: list[ResearchInsight],
        incoming: list[ResearchInsight],
    ) -> list[ResearchInsight]:
        now = _now()
        result = [ResearchInsight.from_dict(item.to_dict()) for item in existing]
        index = {_identity(item): item for item in result}
        for insight in incoming:
            if not insight.id:
                insight.id = _insight_id(insight.type, insight.summary, insight.related_operators)
            key = _identity(insight)
            current = index.get(key)
            if current is None:
                self._apply_soft_contradictions(result, insight)
                result.append(insight)
                index[key] = insight
                continue
            current.support_count = max(current.support_count, insight.support_count)
            current.contradiction_count = max(current.contradiction_count, insight.contradiction_count)
            current.confidence = max(current.confidence, insight.confidence)
            current.freshness_score = max(current.freshness_score, insight.freshness_score)
            current.decay_score = max(current.decay_score, insight.decay_score)
            current.source_rounds = sorted(set(current.source_rounds + insight.source_rounds))
            current.related_operators = _merge_strings(current.related_operators, insight.related_operators, limit=12)
            current.market_tags = _merge_strings(current.market_tags, insight.market_tags, limit=10)
            current.updated_at = now
            current.extra.update(insight.extra)
        result.sort(key=lambda item: (item.confidence, item.support_count, item.freshness_score), reverse=True)
        return result

    def prune_stale(self, insights: list[ResearchInsight]) -> list[ResearchInsight]:
        result: list[ResearchInsight] = []
        for insight in insights:
            if insight.confidence < 0.25 and insight.support_count < 3:
                continue
            if insight.decay_score < 0.15:
                continue
            result.append(insight)
        return result[:200]

    def _apply_soft_contradictions(self, existing: list[ResearchInsight], incoming: ResearchInsight) -> None:
        incoming_ops = set(incoming.related_operators)
        if not incoming_ops:
            return
        for item in existing:
            if item.type != incoming.type:
                continue
            if not (incoming_ops & set(item.related_operators)):
                continue
            if _identity(item) == _identity(incoming):
                continue
            item.contradiction_count += 1
            item.confidence = max(0.0, item.confidence * 0.92)

    def _load_state(self) -> dict[str, Any]:
        data = safe_read_json(self.state_file, {})
        return data if isinstance(data, dict) else {}

    def _save_state(self, sample_count: int, *, generated: int) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(
            self.state_file,
            {
                "last_sample_count": int(sample_count),
                "last_generated_count": int(generated),
                "last_distilled_at": _now(),
                "schema_version": "1.0",
            },
        )


def _identity(insight: ResearchInsight) -> str:
    return "|".join(
        [
            insight.type,
            _normalize(insight.summary),
            ",".join(sorted({item.lower() for item in insight.related_operators})),
        ]
    )


def _insight_id(insight_type: str, summary: str, operators: list[str]) -> str:
    digest = hashlib.sha1(
        f"{insight_type}|{_normalize(summary)}|{','.join(sorted(operators))}".encode("utf-8", errors="ignore")
    ).hexdigest()
    return f"insight:{digest[:16]}"


def _normalize(text: str) -> str:
    return " ".join((text or "").lower().split())


def _merge_strings(left: list[str], right: list[str], *, limit: int) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in left + right:
        if not value or value in seen:
            continue
        result.append(value)
        seen.add(value)
        if len(result) >= limit:
            break
    return result


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")
