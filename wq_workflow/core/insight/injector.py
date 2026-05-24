from __future__ import annotations

import re
from typing import Any

from ..ast import walk
from ..parser import ExpressionParser, ParseError
from .models import ResearchInsight


class InsightInjector:
    def top_k(self, insights: list[ResearchInsight], context: dict[str, Any], *, k: int = 5) -> list[ResearchInsight]:
        if not insights:
            return []
        current_ops = _operators(str(context.get("current_expression") or ""))
        family = str(context.get("behavior_family") or "").lower()
        goal_text = _goal_text(context)
        ranked = []
        for insight in insights:
            if insight.confidence < 0.2 or not insight.summary:
                continue
            score = self._score(insight, current_ops=current_ops, family=family, goal_text=goal_text)
            ranked.append((score, insight))
        ranked.sort(key=lambda item: item[0], reverse=True)
        return [insight for _score, insight in ranked[: max(1, int(k))]]

    def format_for_prompt(self, insights: list[ResearchInsight], *, max_chars: int = 900) -> str:
        lines: list[str] = []
        total = 0
        for insight in insights:
            line = f"- [{insight.confidence:.2f}] {_shorten(insight.summary, 180)}"
            if total + len(line) + 1 > max_chars:
                break
            lines.append(line)
            total += len(line) + 1
        return "\n".join(lines)

    def _score(self, insight: ResearchInsight, *, current_ops: set[str], family: str, goal_text: str) -> float:
        related = {item.lower() for item in insight.related_operators}
        overlap = len(current_ops & related) / max(len(related), 1)
        family_match = 0.0
        if family and family in {tag.lower() for tag in insight.market_tags}:
            family_match = 0.18
        goal_match = 0.0
        summary = insight.summary.lower()
        for token in _keywords(goal_text):
            if token in summary:
                goal_match += 0.04
        contradiction_penalty = min(0.25, insight.contradiction_count * 0.03)
        return (
            insight.confidence * 0.58
            + insight.freshness_score * 0.12
            + insight.decay_score * 0.10
            + min(0.16, overlap * 0.16)
            + family_match
            + min(0.14, goal_match)
            - contradiction_penalty
        )


def _operators(expression: str) -> set[str]:
    try:
        ast = ExpressionParser().parse(expression)
        return {node.name.lower() for node in walk(ast) if node.type == "operator"}
    except (ParseError, ValueError, RecursionError):
        return {item.lower() for item in re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(", expression or "")}


def _goal_text(context: dict[str, Any]) -> str:
    parts = [
        str(context.get("mutation_goal") or ""),
        str(context.get("current_strategy") or ""),
        str(context.get("diversity_requirement") or ""),
    ]
    failures = context.get("recent_failed_patterns")
    if isinstance(failures, list):
        parts.extend(str(item) for item in failures[:3])
    return " ".join(parts).lower()


def _keywords(text: str) -> set[str]:
    allowed = {
        "turnover",
        "sharpe",
        "fitness",
        "correlation",
        "neutralize",
        "bucket",
        "rank",
        "decay",
        "window",
        "failure",
        "operator",
        "group",
        "momentum",
        "reversion",
    }
    return {token for token in re.findall(r"[a-z_]{4,}", text or "") if token in allowed}


def _shorten(text: str, limit: int) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."
