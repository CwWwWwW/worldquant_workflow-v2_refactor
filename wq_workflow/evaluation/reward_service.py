from __future__ import annotations

from typing import Any

from wq_workflow.core_types import PlatformSCResult, QualityResult, RewardResult, SimulationResult


class RewardService:
    """Stable wrapper around the legacy RewardEngine; reward semantics remain unchanged."""

    def __init__(self, engine: Any | None = None, config: Any | None = None) -> None:
        self.config = config
        if engine is None:
            try:
                from wq_workflow.reward_engine import RewardEngine

                engine = RewardEngine()
            except Exception:
                engine = None
        self.engine = engine

    def compute(self, simulation_result: SimulationResult | dict[str, Any] | None, quality_result: QualityResult | dict[str, Any] | None = None, platform_sc: PlatformSCResult | dict[str, Any] | None = None) -> RewardResult:
        sim = simulation_result.to_dict() if hasattr(simulation_result, "to_dict") else (simulation_result or {})
        quality = quality_result.to_dict() if hasattr(quality_result, "to_dict") else (quality_result or {})
        sc = platform_sc.to_dict() if hasattr(platform_sc, "to_dict") else (platform_sc or {})
        metrics = dict(sim.get("metrics") or sim)
        try:
            if self.engine is not None and hasattr(self.engine, "calculate_reward"):
                try:
                    breakdown = self.engine.calculate_reward(metrics, quality=quality, platform_sc=sc)
                except TypeError:
                    breakdown = self.engine.calculate_reward(metrics)
                payload = breakdown.to_dict() if hasattr(breakdown, "to_dict") else (breakdown if isinstance(breakdown, dict) else getattr(breakdown, "__dict__", {}))
                reward = float(payload.get("final_reward", payload.get("reward", payload.get("total", 0.0))) or 0.0)
                return RewardResult(reward=reward, reward_components=dict(payload), reward_version="legacy", raw_payload={"breakdown": payload})
        except Exception as exc:
            return RewardResult(reward=0.0, reward_components={"error": str(exc)}, reward_version="legacy", raw_payload={"simulation_result": sim})
        return RewardResult(reward=float(metrics.get("reward", metrics.get("score", 0.0)) or 0.0), reward_components=metrics, reward_version="legacy", raw_payload={"simulation_result": sim, "quality": quality, "platform_sc": sc})
