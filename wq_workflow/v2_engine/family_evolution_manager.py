from __future__ import annotations

from typing import Any

from ..safe_io import finite_float
from .behavior_fingerprint import build_behavior_fingerprint
from .family_router import FamilyRouter


class FamilyEvolutionManager:
    def __init__(self, router: FamilyRouter | None = None) -> None:
        self.router = router or FamilyRouter()

    def select_parent(
        self,
        rows: list[dict[str, Any]],
        *,
        current_family: str = "",
        fallback: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        if not rows:
            return fallback
        family = (current_family or "").lower()
        enriched = [self._with_family(row) for row in rows]
        same_family = [row for row in enriched if family and row.get("behavior_family") == family]
        candidates = same_family or [row for row in enriched if row.get("behavior_family") not in {"legacy", ""}] or enriched
        candidates.sort(key=_selection_score, reverse=True)
        return candidates[0] if candidates else fallback

    def inheritance_metadata(
        self,
        *,
        parent_family: str,
        child_family: str,
        parent_reward: float = 0.0,
    ) -> dict[str, Any]:
        same_family = parent_family == child_family and child_family not in {"", "legacy"}
        inheritance_weight = 1.0 if same_family else 0.35
        return {
            "parent_family": parent_family or "legacy",
            "child_family": child_family or "legacy",
            "inheritance_weight": inheritance_weight,
            "inherited_reward": round(finite_float(parent_reward) * inheritance_weight, 6),
        }

    def _with_family(self, row: dict[str, Any]) -> dict[str, Any]:
        if row.get("behavior_family"):
            return row
        expression = str(row.get("expression") or row.get("code") or "")
        fingerprint = row.get("behavior_fingerprint") if isinstance(row.get("behavior_fingerprint"), dict) else None
        if not fingerprint:
            fingerprint = build_behavior_fingerprint(expression)
        clone = dict(row)
        clone["behavior_fingerprint"] = fingerprint
        clone["behavior_family"] = self.router.classify(expression, fingerprint)
        return clone


def _selection_score(row: dict[str, Any]) -> float:
    metrics = row.get("metrics") if isinstance(row.get("metrics"), dict) else {}
    reward = finite_float(row.get("reward"))
    sharpe = finite_float(metrics.get("sharpe"))
    fitness = finite_float(metrics.get("fitness"))
    diversity = finite_float(row.get("diversity_score"), 0.5)
    estimated_self_corr = finite_float(row.get("estimated_self_corr"))
    passed_bonus = 0.25 if row.get("passed") or row.get("template_success") else 0.0
    return reward * 0.45 + sharpe * 0.20 + fitness * 0.15 + diversity * 0.15 + passed_bonus - estimated_self_corr * 0.10
