from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from ..fast_expression import validate_fast_expression
from .adaptive_mutation_scheduler import MutationSchedule
from .behavior_fingerprint import build_behavior_fingerprint


TRADE_WHEN_TEMPLATES = [
    "volume > adv20",
    "abs(returns) > 0.02",
    "ts_std_dev(returns, 20) > 0.02",
    "ts_rank(volume, 20) > 0.5",
    "rank(cap) > 0.2",
]

GROUP_FIELDS = ["sector", "industry", "subindustry", "exchange", "market"]
GROUP_OPERATORS = ["group_neutralize", "group_rank", "group_zscore"]
BUCKET_FIELDS = ["cap", "volume", "returns"]
BUCKET_RANGES = ["0.1,1,0.1", "0.05,1,0.05", "0.02,1,0.02"]


@dataclass(slots=True)
class V2MutationCandidate:
    expression: str
    mutation_type: str
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RegimeMutator:
    def generate(
        self,
        expression: str,
        schedule: MutationSchedule | None = None,
        fingerprint: dict[str, Any] | None = None,
        *,
        limit: int = 8,
    ) -> list[V2MutationCandidate]:
        fingerprint = fingerprint or build_behavior_fingerprint(expression)
        requested = list(schedule.recommended_mutations if schedule else [])
        if not requested:
            requested = ["trade_when_mutation", "group_mutation", "bucket_mutation"]
        signal = _final_expression(expression)
        candidates: list[V2MutationCandidate] = []
        for mutation in requested:
            if mutation == "trade_when_mutation":
                candidates.extend(self.trade_when_mutations(signal, fingerprint))
            elif mutation == "group_mutation":
                candidates.extend(self.group_mutations(signal))
            elif mutation == "bucket_mutation":
                candidates.extend(self.bucket_mutations(signal))
            if len(candidates) >= limit:
                break
        return _dedupe_valid(candidates)[:limit]

    def trade_when_mutations(self, signal: str, fingerprint: dict[str, Any] | None = None) -> list[V2MutationCandidate]:
        if re.search(r"\btrade_when\s*\(", signal):
            return [
                V2MutationCandidate(
                    expression=_replace_trade_when_condition(signal, condition),
                    mutation_type="trade_when_mutation",
                    description=f"replace trade_when condition with {condition}",
                    metadata={"condition": condition},
                )
                for condition in TRADE_WHEN_TEMPLATES
            ]
        return [
            V2MutationCandidate(
                expression=f"trade_when({condition}, {signal}, -1)",
                mutation_type="trade_when_mutation",
                description=f"gate active regime with {condition}",
                metadata={"condition": condition},
            )
            for condition in TRADE_WHEN_TEMPLATES
        ]

    def group_mutations(self, signal: str) -> list[V2MutationCandidate]:
        candidates: list[V2MutationCandidate] = []
        for group in GROUP_FIELDS:
            for operator in GROUP_OPERATORS:
                candidates.append(
                    V2MutationCandidate(
                        expression=f"{operator}({signal}, {group})",
                        mutation_type="group_mutation",
                        description=f"apply {operator} by {group}",
                        metadata={"group": group, "operator": operator},
                    )
                )
        return candidates

    def bucket_mutations(self, signal: str) -> list[V2MutationCandidate]:
        candidates: list[V2MutationCandidate] = []
        for field in BUCKET_FIELDS:
            bucket_source = "ts_std_dev(returns, 20)" if field == "returns" else field
            for bucket_range in BUCKET_RANGES:
                bucket = f'bucket(rank({bucket_source}), range="{bucket_range}")'
                candidates.append(
                    V2MutationCandidate(
                        expression=f"group_neutralize({signal}, {bucket})",
                        mutation_type="bucket_mutation",
                        description=f"neutralize by bucket(rank({bucket_source})) range {bucket_range}",
                        metadata={"bucket_source": bucket_source, "range": bucket_range},
                    )
                )
        return candidates


def _final_expression(expression: str) -> str:
    lines = [line.strip().rstrip(";") for line in (expression or "").splitlines() if line.strip()]
    if not lines:
        return "rank(returns)"
    last = lines[-1]
    if "=" in last and not re.search(r"[<>!]=|==", last):
        return str(last.split("=", 1)[-1]).strip() or "rank(returns)"
    return last


def _replace_trade_when_condition(expression: str, condition: str) -> str:
    match = re.search(r"\btrade_when\s*\(", expression)
    if not match:
        return f"trade_when({condition}, {expression}, -1)"
    start = match.end()
    comma = _first_top_level_comma(expression, start)
    if comma < 0:
        return f"trade_when({condition}, {expression}, -1)"
    return expression[:start] + condition + expression[comma:]


def _first_top_level_comma(text: str, start: int) -> int:
    depth = 0
    quote = ""
    for index in range(start, len(text)):
        char = text[index]
        if quote:
            if char == quote:
                quote = ""
            continue
        if char in {'"', "'"}:
            quote = char
            continue
        if char == "(":
            depth += 1
        elif char == ")":
            if depth == 0:
                return -1
            depth -= 1
        elif char == "," and depth == 0:
            return index
    return -1


def _dedupe_valid(candidates: list[V2MutationCandidate]) -> list[V2MutationCandidate]:
    seen: set[str] = set()
    result: list[V2MutationCandidate] = []
    for candidate in candidates:
        key = re.sub(r"\s+", "", candidate.expression.lower())
        if key in seen:
            continue
        seen.add(key)
        if validate_fast_expression(candidate.expression, enable_v2_engine=True):
            continue
        result.append(candidate)
    return result
