from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .core.evolution import PendingRewardManager, SurvivalMemoryManager, TemplatePopulationController
from .mutation_engine import complexity_score, normalize_turnover
from .platform_sc import sc_payload_from_metrics, sc_reward_multiplier
from .reward_migration import MigrationController, MigrationDecision
from .safe_io import finite_float


@dataclass(slots=True)
class RewardBreakdown:
    legacy_reward: float = 0.0
    final_reward: float = 0.0
    sharpe_score: float = 0.0
    fitness_score: float = 0.0
    robustness_score: float = 0.0
    diversity_score: float = 0.0
    lineage_score: float = 0.0
    correlation_score: float = 0.0
    turnover_penalty: float = 0.0
    complexity_penalty: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RewardEngine:
    def __init__(
        self,
        *,
        expression_length_limit: int = 700,
        operator_count_limit: int = 24,
        migration_controller: MigrationController | None = None,
        enable_migration: bool = True,
        enable_survival_memory: bool = True,
        enable_pending_reward: bool = True,
        enable_template_governance: bool = True,
        enable_exploration_pressure: bool = True,
        enable_adaptive_legacy: bool = True,
        survival_manager: SurvivalMemoryManager | None = None,
        pending_reward_manager: PendingRewardManager | None = None,
        template_controller: TemplatePopulationController | None = None,
    ) -> None:
        self.expression_length_limit = expression_length_limit
        self.operator_count_limit = operator_count_limit
        self.enable_migration = enable_migration
        self.migration_controller = migration_controller or MigrationController(enable_adaptive_legacy=enable_adaptive_legacy)
        self.enable_survival_memory = enable_survival_memory
        self.enable_pending_reward = enable_pending_reward
        self.enable_template_governance = enable_template_governance
        self.enable_exploration_pressure = enable_exploration_pressure
        self.survival_manager = survival_manager or SurvivalMemoryManager()
        self.pending_reward_manager = pending_reward_manager or PendingRewardManager()
        self.template_controller = template_controller or TemplatePopulationController()
        self.last_breakdown: RewardBreakdown | dict[str, Any] | None = None
        self.last_migration_decision: MigrationDecision | None = None
        self.last_evolution_metadata: dict[str, Any] = {}

    def calculate_reward(
        self,
        before_metrics: dict[str, float] | None,
        after_metrics: dict[str, float] | None,
        expression_after: str,
        *,
        novelty_score: float = 0.0,
        stability_score: float = 0.0,
        diversity_score: float = 0.0,
        lineage_success_rate: float = 0.0,
        alpha_id: str = "",
        v2_reward: float | None = None,
        v2_breakdown: RewardBreakdown | dict[str, Any] | None = None,
        migration_context: dict[str, Any] | None = None,
    ) -> float:
        self.last_evolution_metadata = {}
        legacy = _reward_cap(
            legacy_reward(
                before_metrics,
                after_metrics,
                expression_after,
                novelty_score=novelty_score,
                stability_score=stability_score,
                diversity_score=diversity_score,
                lineage_success_rate=lineage_success_rate,
                expression_length_limit=self.expression_length_limit,
                operator_count_limit=self.operator_count_limit,
            )
        )
        breakdown = v2_breakdown or self._default_v2_breakdown(
            before_metrics,
            after_metrics,
            expression_after,
            legacy_reward_value=legacy,
            v2_reward=v2_reward,
            stability_score=stability_score,
            diversity_score=diversity_score,
            lineage_success_rate=lineage_success_rate,
        )
        self._attach_v2_context(breakdown, migration_context or {})
        legacy_for_blend = legacy
        sc_multiplier, sc_penalty = sc_reward_multiplier(after_metrics or {})
        if sc_multiplier != 1.0:
            legacy_for_blend = _reward_cap(legacy_for_blend * sc_multiplier)
            _set_breakdown_final_reward(breakdown, _breakdown_final_reward(breakdown, legacy) * sc_multiplier)
            _merge_breakdown_metadata(
                breakdown,
                {
                    "platform_sc_penalty": {
                        **sc_penalty,
                        "multiplier": sc_multiplier,
                        **sc_payload_from_metrics(after_metrics or {}),
                    }
                },
            )
        elif sc_penalty:
            _merge_breakdown_metadata(breakdown, {"platform_sc": sc_penalty})
        if self.enable_migration and alpha_id:
            breakdown = self._apply_evolution_layer(
                alpha_id=alpha_id,
                legacy_reward_value=legacy_for_blend,
                breakdown=breakdown,
                context=migration_context or {},
            )
        self.last_breakdown = breakdown
        if not self.enable_migration or not alpha_id:
            return legacy_for_blend
        try:
            decision = self.migration_controller.blend_reward(
                alpha_id=alpha_id,
                legacy_reward=legacy_for_blend,
                v2_breakdown=breakdown,
                context=migration_context or {},
            )
        except Exception:
            self.last_migration_decision = None
            return legacy_for_blend
        self.last_migration_decision = decision
        return _reward_cap(decision.final_reward)

    def record_evolution_feedback(
        self,
        *,
        alpha_id: str,
        reward: float,
        passed: bool,
        generation: int = 0,
        template: str = "",
        operator: str = "",
        parent_id: str = "",
        lineage_depth: int = 0,
        pool_rows: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if not alpha_id:
            return {}
        metadata: dict[str, Any] = {"alpha_id": alpha_id}
        if self.enable_survival_memory:
            self.survival_manager.register_alpha(
                alpha_id,
                generation_created=generation,
                behavior_family=template,
                template=template,
                operator=operator,
                parent=parent_id,
                lineage_depth=lineage_depth,
            )
            survival_record = self.survival_manager.update_survival(alpha_id, passed=passed)
            if parent_id and passed:
                self.survival_manager.increment_children_success(parent_id)
            metadata["survival"] = survival_record
        if self.enable_pending_reward:
            pending_base = finite_float(self.last_evolution_metadata.get("pending_reward_base"), reward)
            pending_record = self.pending_reward_manager.register_pending_reward(
                alpha_id,
                pending_base,
                created_generation=generation,
                behavior_family=template,
                template=template,
                operator=operator,
                lineage_depth=lineage_depth,
                lineage_root=parent_id,
            )
            metadata["pending_reward"] = pending_record
        if self.enable_template_governance and pool_rows is not None:
            metadata["template_stats"] = self.template_controller.update_template_stats(pool_rows)
        return metadata

    def _default_v2_breakdown(
        self,
        before_metrics: dict[str, float] | None,
        after_metrics: dict[str, float] | None,
        expression_after: str,
        *,
        legacy_reward_value: float,
        v2_reward: float | None,
        stability_score: float,
        diversity_score: float,
        lineage_success_rate: float,
    ) -> RewardBreakdown:
        before = before_metrics or {}
        after = after_metrics or {}
        sharpe_delta = _metric(after, "sharpe") - _metric(before, "sharpe")
        fitness_delta = _metric(after, "fitness") - _metric(before, "fitness")
        turnover_penalty = (normalize_turnover(after.get("turnover", 0.0)) - normalize_turnover(before.get("turnover", 0.0))) / 100.0
        complexity = complexity_score(expression_after)
        complexity_penalty = 0.0
        if len(expression_after or "") > self.expression_length_limit:
            complexity_penalty += 0.3
        if complexity.get("operator_count", 0) > self.operator_count_limit:
            complexity_penalty += 0.2
        final = legacy_reward_value if v2_reward is None else _safe_float(v2_reward, legacy_reward_value)
        final = _reward_cap(final)
        return RewardBreakdown(
            legacy_reward=legacy_reward_value,
            final_reward=round(final, 6),
            sharpe_score=round(sharpe_delta, 6),
            fitness_score=round(fitness_delta, 6),
            robustness_score=round(_clamp(stability_score), 6),
            diversity_score=round(_clamp(diversity_score), 6),
            lineage_score=round(_clamp(lineage_success_rate), 6),
            correlation_score=0.0,
            turnover_penalty=round(turnover_penalty, 6),
            complexity_penalty=round(complexity_penalty, 6),
            metadata={
                "migration_ready": True,
                "v2_source": "provided" if v2_reward is not None else "legacy_shadow_fallback",
                "complexity": complexity,
            },
        )

    def _attach_v2_context(self, breakdown: RewardBreakdown | dict[str, Any], context: dict[str, Any]) -> None:
        if not context:
            return
        estimated = context.get("estimated_self_corr")
        behavior_family = context.get("behavior_family")
        fingerprint = context.get("behavior_fingerprint")
        inheritance = context.get("family_reward_inheritance")
        sc_payload = sc_payload_from_metrics(context)
        if isinstance(breakdown, RewardBreakdown):
            if estimated is not None:
                breakdown.correlation_score = round(1.0 - _clamp(finite_float(estimated)), 6)
            breakdown.metadata.update(
                {
                    key: value
                    for key, value in {
                        "estimated_self_corr": estimated,
                        "behavior_family": behavior_family,
                        "behavior_fingerprint": fingerprint,
                        "family_reward_inheritance": inheritance,
                        **sc_payload,
                    }.items()
                    if value not in (None, "", {})
                }
            )
        elif isinstance(breakdown, dict):
            metadata = breakdown.setdefault("metadata", {})
            if isinstance(metadata, dict):
                metadata.update(
                    {
                        key: value
                        for key, value in {
                            "estimated_self_corr": estimated,
                            "behavior_family": behavior_family,
                            "behavior_fingerprint": fingerprint,
                            "family_reward_inheritance": inheritance,
                            **sc_payload,
                        }.items()
                        if value not in (None, "", {})
                    }
                )
            if estimated is not None:
                breakdown["correlation_score"] = round(1.0 - _clamp(finite_float(estimated)), 6)

    def _apply_evolution_layer(
        self,
        *,
        alpha_id: str,
        legacy_reward_value: float,
        breakdown: RewardBreakdown | dict[str, Any],
        context: dict[str, Any],
    ) -> RewardBreakdown | dict[str, Any]:
        base_reward = _breakdown_final_reward(breakdown, legacy_reward_value)
        template = _template_from_context(context)
        operator = str(context.get("mutation_type") or context.get("operator") or "unknown")
        lineage = str(context.get("lineage_root") or context.get("parent_id") or "")
        generation = _safe_int(context.get("generation") or context.get("iteration"), 0)
        long_term_score = 0.0
        if self.enable_survival_memory:
            long_term_score = self.survival_manager.compute_long_term_score(alpha_id)

        settlement = {
            "released_total": 0.0,
            "canceled_total": 0.0,
            "released_count": 0,
            "canceled_count": 0,
            "adjustment": 0.0,
        }
        if self.enable_pending_reward:
            settlement = self.pending_reward_manager.settle_rewards(
                current_generation=generation,
                survival_manager=self.survival_manager,
                current_behavior_family=template,
                current_template=template,
                current_operator=operator,
                current_lineage=lineage,
            )

        full_evolution_reward = base_reward + long_term_score + finite_float(settlement.get("adjustment"))
        immediate_evolution_reward = (
            self.pending_reward_manager.immediate_reward(full_evolution_reward)
            if self.enable_pending_reward
            else full_evolution_reward
        )
        adjusted_evolution_reward = immediate_evolution_reward
        template_penalty: dict[str, Any] = {}
        if self.enable_template_governance:
            adjusted_evolution_reward, template_penalty = self.template_controller.apply_penalty(
                immediate_evolution_reward,
                template,
            )
            context["template_diversity"] = self.template_controller.template_diversity()
            if self.enable_exploration_pressure:
                context["exploration_pressure"] = self.template_controller.pressure_for_family(template)
                context["exploration_adjustments"] = {
                    "random_mutation": self.template_controller.increase_random_mutation(template),
                    "cross_family_mutation": self.template_controller.increase_cross_family_mutation(template),
                    "operator_diversity": self.template_controller.increase_operator_diversity(template),
                }
        adjusted_evolution_reward = _reward_cap(adjusted_evolution_reward)
        metadata = {
            "enabled": True,
            "base_reward": round(base_reward, 6),
            "long_term_score": round(long_term_score, 6),
            "pending_settlement": settlement,
            "pending_reward_base": round(full_evolution_reward, 6),
            "immediate_evolution_reward": round(immediate_evolution_reward, 6),
            "template_penalty": template_penalty,
            "final_evolution_reward": round(adjusted_evolution_reward, 6),
        }
        self.last_evolution_metadata = metadata
        _set_breakdown_final_reward(breakdown, adjusted_evolution_reward)
        _merge_breakdown_metadata(breakdown, {"evolution_layer": metadata})
        return breakdown


def legacy_reward(
    before_metrics: dict[str, float] | None,
    after_metrics: dict[str, float] | None,
    expression_after: str,
    *,
    novelty_score: float = 0.0,
    stability_score: float = 0.0,
    diversity_score: float = 0.0,
    lineage_success_rate: float = 0.0,
    expression_length_limit: int = 700,
    operator_count_limit: int = 24,
) -> float:
    before = before_metrics or {}
    after = after_metrics or {}
    sharpe_delta = _metric(after, "sharpe") - _metric(before, "sharpe")
    fitness_delta = _metric(after, "fitness") - _metric(before, "fitness")
    turnover_penalty = (normalize_turnover(after.get("turnover", 0.0)) - normalize_turnover(before.get("turnover", 0.0))) / 100.0

    reward = sharpe_delta * 0.45 + fitness_delta * 0.35 - turnover_penalty * 0.2
    reward += _clamp(novelty_score) * 0.08
    reward += _clamp(stability_score) * 0.06
    reward += _clamp(diversity_score) * 0.08
    reward += _clamp(lineage_success_rate) * 0.05

    if normalize_turnover(after.get("turnover", 0.0)) > 75.0:
        reward -= 0.5
    if len(expression_after or "") > expression_length_limit:
        reward -= 0.3
    if complexity_score(expression_after).get("operator_count", 0) > operator_count_limit:
        reward -= 0.2
    return round(_reward_cap(reward), 6)


def metric_delta(before_metrics: dict[str, float] | None, after_metrics: dict[str, float] | None) -> dict[str, float]:
    before = before_metrics or {}
    after = after_metrics or {}
    keys = sorted(set(before) | set(after) | {"sharpe", "fitness", "turnover"})
    result: dict[str, float] = {}
    for key in keys:
        after_value = normalize_turnover(after.get(key, 0.0)) if key == "turnover" else _metric(after, key)
        before_value = normalize_turnover(before.get(key, 0.0)) if key == "turnover" else _metric(before, key)
        result[key] = round(after_value - before_value, 6)
    return result


def _metric(metrics: dict[str, Any], key: str) -> float:
    return finite_float(metrics.get(key, 0.0))


def _clamp(value: float) -> float:
    number = finite_float(value)
    return max(0.0, min(1.0, number))


def _safe_float(value: Any, default: float) -> float:
    return finite_float(value, default)


def _reward_cap(value: Any) -> float:
    return finite_float(value, 0.0, minimum=-10.0, maximum=10.0)


def _breakdown_final_reward(breakdown: RewardBreakdown | dict[str, Any], fallback: float) -> float:
    if isinstance(breakdown, dict):
        return _safe_float(breakdown.get("final_reward"), fallback)
    return _safe_float(getattr(breakdown, "final_reward", fallback), fallback)


def _set_breakdown_final_reward(breakdown: RewardBreakdown | dict[str, Any], value: float) -> None:
    if isinstance(breakdown, dict):
        breakdown["final_reward"] = round(value, 6)
    else:
        breakdown.final_reward = round(value, 6)


def _merge_breakdown_metadata(breakdown: RewardBreakdown | dict[str, Any], payload: dict[str, Any]) -> None:
    if isinstance(breakdown, dict):
        metadata = breakdown.setdefault("metadata", {})
        if isinstance(metadata, dict):
            metadata.update(payload)
        return
    breakdown.metadata.update(payload)


def _template_from_context(context: dict[str, Any]) -> str:
    return str(context.get("behavior_family") or context.get("template") or "legacy")


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
