from __future__ import annotations

from typing import Any

from ...mutation_engine import complexity_score, normalize_turnover
from ...safe_io import finite_float


class AlphaSimulator:
    def __init__(
        self,
        *,
        low_confidence_threshold: float = 0.2,
        skip_threshold: float = 0.18,
        never_skip_if_parent_reward_above: float = 1.0,
        skip_enabled: bool = True,
    ) -> None:
        self.low_confidence_threshold = finite_float(low_confidence_threshold, 0.2, minimum=0.0, maximum=1.0)
        self.skip_threshold = finite_float(skip_threshold, 0.18, minimum=0.0, maximum=1.0)
        self.never_skip_if_parent_reward_above = finite_float(never_skip_if_parent_reward_above, 1.0)
        self.skip_enabled = bool(skip_enabled)

    def evaluate(self, candidate: dict[str, Any]) -> dict[str, Any]:
        expression = str(candidate.get("expression") or candidate.get("code") or "")
        metrics = candidate.get("metrics") if isinstance(candidate.get("metrics"), dict) else {}
        complexity = candidate.get("complexity") if isinstance(candidate.get("complexity"), dict) else complexity_score(expression)
        score = 0.0
        flags: list[str] = []

        operator_count = finite_float(complexity.get("operator_count"), 0.0, minimum=0.0)
        expression_length = len(expression)
        historical_corr = finite_float(candidate.get("historical_corr", candidate.get("estimated_self_corr")), 0.0, minimum=0.0, maximum=1.0)
        turnover = normalize_turnover(metrics.get("turnover", candidate.get("turnover", 0.0)))

        if operator_count <= 20:
            score += 0.25
        else:
            flags.append("high_complexity")
        if expression_length <= 512:
            score += 0.20
        else:
            flags.append("long_expression")
        if historical_corr < 0.7:
            score += 0.25
        else:
            flags.append("high_correlation")
        if turnover <= 40:
            score += 0.20
        elif turnover > 70:
            flags.append("high_turnover")
        family = str(candidate.get("family") or candidate.get("behavior_family") or "")
        if family and family != "legacy":
            score += 0.10

        score = round(max(0.0, min(1.0, score)), 6)
        if score < self.low_confidence_threshold:
            flags.append("low_confidence")
        return {
            "simulator_score": score,
            "flags": flags,
            "low_confidence": "low_confidence" in flags,
            "recommendation": "continue_backtest_observe_low_confidence"
            if "low_confidence" in flags
            else "continue_backtest",
            "authority": "observer_only",
        }

    def should_skip(
        self,
        candidate: dict[str, Any],
        context: dict[str, Any] | None = None,
        *,
        experimental: bool = False,
    ) -> tuple[bool, dict[str, Any]]:
        observation = self.evaluate(candidate)
        observation["context"] = context or {}
        observation["skipped"] = False
        observation["skipped_reason"] = ""
        observation["parent_reward"] = finite_float(candidate.get("parent_reward"), 0.0)
        if not experimental or not self.skip_enabled:
            observation["authority"] = "advisory_only"
            observation["decision_authority"] = "none"
            return False, observation
        source = str(candidate.get("candidate_source") or candidate.get("source") or "").strip().lower()
        protected_sources = {"seed", "current_code", "legacy_parent", "template_initial"}
        if source in protected_sources:
            observation["authority"] = "experimental_decision"
            observation["decision_authority"] = "ga_rl_policy"
            observation["skipped_reason"] = "protected_candidate_source"
            return False, observation
        if not bool(candidate.get("is_pending_candidate", False)):
            observation["authority"] = "experimental_decision"
            observation["decision_authority"] = "ga_rl_policy"
            observation["skipped_reason"] = "not_pending_candidate"
            return False, observation
        if observation["parent_reward"] >= self.never_skip_if_parent_reward_above:
            observation["authority"] = "experimental_decision"
            observation["decision_authority"] = "ga_rl_policy"
            observation["skipped_reason"] = "strong_parent"
            return False, observation
        if finite_float(observation.get("simulator_score"), 0.0) < self.skip_threshold:
            observation["skipped"] = True
            observation["skipped_reason"] = "simulator_score_below_threshold"
            observation["authority"] = "experimental_decision"
            observation["decision_authority"] = "ga_rl_policy"
            observation["recommendation"] = "skip_backtest"
            return True, observation
        observation["authority"] = "experimental_decision"
        observation["decision_authority"] = "ga_rl_policy"
        return False, observation
