from __future__ import annotations

from typing import Any

from .behavior_fingerprint import FAMILY_NAMES, build_behavior_fingerprint


class FamilyRouter:
    """Deterministic family classifier for behavior-aware evolution."""

    def classify(self, expression: str, fingerprint: dict[str, Any] | None = None) -> str:
        fp = fingerprint if isinstance(fingerprint, dict) else build_behavior_fingerprint(expression)
        family = str(fp.get("family") or "").strip().lower()
        if family in FAMILY_NAMES and family != "legacy":
            return family
        if family == "legacy":
            return "legacy"

        scores = {
            "event": 0.8 if fp.get("trade_when") or fp.get("event_driven") else 0.0,
            "group": min(1.0, _number(fp.get("group_ops")) * 0.35 + _number(fp.get("bucket_ops")) * 0.25),
            "momentum": _number(fp.get("momentum_bias")),
            "mean_reversion": _number(fp.get("mean_reversion_bias")),
            "volatility": _number(fp.get("volatility_bias")),
        }
        active = [name for name, score in scores.items() if score >= 0.45]
        if len(active) >= 2:
            return "hybrid"
        best = max(scores.items(), key=lambda item: item[1])
        return best[0] if best[1] >= 0.30 else "hybrid"


def _number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
