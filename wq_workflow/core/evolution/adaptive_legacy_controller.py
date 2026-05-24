from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from ...paths import ADAPTIVE_WEIGHT_LOG_FILE
from ...safe_io import append_jsonl, finite_float


class AdaptiveLegacyController:
    def __init__(
        self,
        log_path: Path = ADAPTIVE_WEIGHT_LOG_FILE,
        *,
        min_legacy_weight: float = 0.15,
        max_legacy_weight: float = 0.85,
    ) -> None:
        self.log_path = log_path
        self.min_legacy_weight = finite_float(min_legacy_weight, 0.15, minimum=0.0, maximum=1.0)
        self.max_legacy_weight = finite_float(max_legacy_weight, 0.85, minimum=self.min_legacy_weight, maximum=1.0)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def compute_legacy_weight(
        self,
        *,
        reward_future_corr: float = 0.0,
        lineage_entropy: float = 1.0,
        rollback_count: int = 0,
        mutation_success: float = 0.5,
        reward_variance: float = 0.0,
        template_diversity: float = 1.0,
    ) -> float:
        raw = (
            1.0
            - finite_float(reward_future_corr) * 0.4
            - finite_float(lineage_entropy, 1.0) * 0.3
            - finite_float(template_diversity, 1.0) * 0.2
            + max(0, int(rollback_count or 0)) * 0.2
        )
        raw += max(0.0, 0.25 - finite_float(mutation_success, 0.5)) * 0.2
        raw += max(0.0, finite_float(reward_variance) - 1.0) * 0.05
        return round(max(self.min_legacy_weight, min(self.max_legacy_weight, raw)), 6)

    def compute_v2_weight(self, legacy_weight: float) -> float:
        return round(max(0.0, min(1.0, 1.0 - finite_float(legacy_weight))), 6)

    def compute_hybrid_reward(
        self,
        legacy_reward: float,
        evolution_reward: float,
        *,
        reward_future_corr: float = 0.0,
        lineage_entropy: float = 1.0,
        rollback_count: int = 0,
        mutation_success: float = 0.5,
        reward_variance: float = 0.0,
        template_diversity: float = 1.0,
    ) -> dict[str, Any]:
        legacy_weight = self.compute_legacy_weight(
            reward_future_corr=reward_future_corr,
            lineage_entropy=lineage_entropy,
            rollback_count=rollback_count,
            mutation_success=mutation_success,
            reward_variance=reward_variance,
            template_diversity=template_diversity,
        )
        v2_weight = self.compute_v2_weight(legacy_weight)
        final_reward = finite_float(legacy_reward) * legacy_weight + finite_float(evolution_reward) * v2_weight
        payload = {
            "legacy_weight": legacy_weight,
            "v2_weight": v2_weight,
            "final_reward": round(final_reward, 6),
            "inputs": {
                "reward_future_corr": finite_float(reward_future_corr),
                "lineage_entropy": finite_float(lineage_entropy, 1.0),
                "rollback_count": max(0, int(rollback_count or 0)),
                "mutation_success": finite_float(mutation_success, 0.5),
                "reward_variance": finite_float(reward_variance),
                "template_diversity": finite_float(template_diversity, 1.0),
            },
        }
        self._log(payload)
        return payload

    def _log(self, payload: dict[str, Any]) -> None:
        append_jsonl(
            self.log_path,
            {
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                **payload,
            },
        )
