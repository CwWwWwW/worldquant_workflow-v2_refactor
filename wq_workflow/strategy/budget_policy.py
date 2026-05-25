from __future__ import annotations

from dataclasses import replace
from typing import Any

from .budget_schema import StrategyBudgetAllocation, StrategyBudgetRule, utc_now_iso
from .portfolio_schema import StrategyState

_BLOCKED_GOVERNANCE = {"blocked", "block", "veto", "vetoed", "disabled", "deny", "denied"}
_HIGH_SC_FLAGS = {"high_sc_risk", "high_risk_estimate", "sc_risk_high", "platform_sc_risk_high"}
_INSUFFICIENT_REASONS = {"insufficient_evidence", "observe_more", "low_sample_count"}


class StrategyBudgetPolicy:
    def __init__(self, config: Any | None = None, logger: Any | None = None) -> None:
        self.config = config
        self.logger = logger

    def default_rules(self) -> list[StrategyBudgetRule]:
        return [
            StrategyBudgetRule(rule_id="strategy_budget_rule:legacy_baseline_floor", rule_type="baseline_floor", description="legacy_baseline advisory floor", enabled=True, priority=10, min_ratio=self.legacy_floor, applies_to_strategy_type="legacy_baseline", reason_code="legacy_baseline_budget_floor"),
            StrategyBudgetRule(rule_id="strategy_budget_rule:random_exploration_floor", rule_type="exploration_floor", description="random exploration advisory floor", enabled=True, priority=20, min_ratio=self.exploration_floor, applies_to_strategy_type="random_exploration", reason_code="random_exploration_budget_floor"),
            StrategyBudgetRule(rule_id="strategy_budget_rule:disabled_zero", rule_type="disabled_zero", description="disabled strategies receive zero advisory budget", enabled=True, priority=30, max_ratio=0.0, applies_to_state="disabled", reason_code="disabled_budget_zero"),
            StrategyBudgetRule(rule_id="strategy_budget_rule:governance_block_zero", rule_type="governance_block_zero", description="governance blocked strategies receive zero advisory budget", enabled=True, priority=40, max_ratio=0.0, reason_code="governance_blocked_budget_zero"),
            StrategyBudgetRule(rule_id="strategy_budget_rule:shadow_cap", rule_type="shadow_cap", description="shadow strategies observe only", enabled=True, priority=50, max_ratio=self.shadow_cap, applies_to_state="shadow", reason_code="shadow_observe_budget"),
            StrategyBudgetRule(rule_id="strategy_budget_rule:challenger_cap", rule_type="challenger_cap", description="challengers receive limited test budget", enabled=True, priority=60, max_ratio=self.challenger_cap, applies_to_state="challenger", reason_code="challenger_test_budget"),
            StrategyBudgetRule(rule_id="strategy_budget_rule:limited_active_cap", rule_type="limited_active_cap", description="limited active strategies remain capped", enabled=True, priority=70, max_ratio=self.limited_active_cap, applies_to_state="limited_active", reason_code="limited_active_scale_limited_budget"),
            StrategyBudgetRule(rule_id="strategy_budget_rule:high_risk_cap", rule_type="high_risk_cap", description="high risk strategies are capped", enabled=True, priority=80, max_ratio=self.high_risk_cap, reason_code="high_risk_budget_cap"),
            StrategyBudgetRule(rule_id="strategy_budget_rule:high_sc_cap", rule_type="high_sc_cap", description="high SC risk strategies are capped", enabled=True, priority=90, max_ratio=self.high_sc_cap, reason_code="high_sc_budget_cap"),
            StrategyBudgetRule(rule_id="strategy_budget_rule:normalization", rule_type="normalization", description="advisory ratios are normalized", enabled=True, priority=100, reason_code="strategy_budget_normalized"),
        ]

    def requested_ratio_from_state(self, state: StrategyState) -> float:
        item = StrategyState.from_dict(state)
        name = self._effective_state(item)
        if name == "disabled":
            return 0.0
        if name == "shadow":
            return min(self.shadow_cap, 0.01)
        if name == "challenger":
            return min(self.challenger_cap, 0.05 + max(0.0, min(1.0, item.score)) * 0.10)
        if name == "limited_active":
            return min(self.limited_active_cap, 0.20 + max(0.0, min(1.0, item.score)) * 0.10)
        if name == "champion":
            return max(self.legacy_floor, 0.60)
        return 0.0

    def cap_for_state(self, state: StrategyState) -> float:
        item = StrategyState.from_dict(state)
        name = self._effective_state(item)
        if name == "disabled":
            return 0.0
        if name == "shadow":
            return self.shadow_cap
        if name == "challenger":
            return self.challenger_cap
        if name == "limited_active":
            return self.limited_active_cap
        if name == "champion":
            return 0.80
        return self.non_champion_cap

    def floor_for_strategy(self, state: StrategyState) -> float:
        item = StrategyState.from_dict(state)
        if self._is_legacy(item):
            return self.legacy_floor
        if self._is_random(item):
            return self.exploration_floor
        if self._effective_state(item) == "champion":
            return self.legacy_floor
        return 0.0

    def status_for_state(self, state: StrategyState) -> str:
        item = StrategyState.from_dict(state)
        if self._is_legacy(item) or self._effective_state(item) == "champion":
            return "baseline"
        if self._is_random(item):
            return "exploration"
        name = self._effective_state(item)
        return {
            "disabled": "blocked",
            "shadow": "observe",
            "challenger": "test",
            "limited_active": "scale_limited",
            "champion": "baseline",
        }.get(name, "hold")

    def apply_risk_guards(self, allocation: StrategyBudgetAllocation) -> StrategyBudgetAllocation:
        item = StrategyBudgetAllocation.from_dict(allocation)
        reasons = list(dict.fromkeys(item.reason_codes or []))
        flags = list(dict.fromkeys(item.risk_flags or []))
        risk_lower = str(item.risk_level or "").strip().lower()
        if item.state == "disabled" or risk_lower == "blocked":
            reasons.append("disabled_budget_zero" if item.state == "disabled" else "risk_blocked_budget_zero")
            return replace(item, suggested_ratio=0.0, requested_ratio=0.0, hard_cap_ratio=0.0, budget_status="blocked", reason_codes=list(dict.fromkeys(reasons)), risk_flags=flags, auto_apply_allowed=False)
        if risk_lower == "high":
            flags.append("high_risk_budget_cap")
            reasons.append("high_risk_budget_cap")
            item.hard_cap_ratio = min(item.hard_cap_ratio, self.high_risk_cap)
            item.suggested_ratio = min(item.suggested_ratio, item.hard_cap_ratio)
        if self._has_high_sc(item):
            flags.append("high_sc_risk")
            reasons.append("high_sc_budget_cap")
            item.hard_cap_ratio = min(item.hard_cap_ratio, self.high_sc_cap)
            item.suggested_ratio = min(item.suggested_ratio, item.hard_cap_ratio)
        if self._insufficient_evidence(item) and item.budget_status not in {"baseline", "exploration"}:
            reasons.append("insufficient_evidence_budget_cap")
            item.hard_cap_ratio = min(item.hard_cap_ratio, self.insufficient_evidence_cap)
            item.suggested_ratio = min(item.suggested_ratio, item.hard_cap_ratio)
        if item.budget_status != "baseline":
            item.hard_cap_ratio = min(item.hard_cap_ratio, self.non_champion_cap)
            item.suggested_ratio = min(item.suggested_ratio, item.hard_cap_ratio)
        item.reason_codes = list(dict.fromkeys(reasons))[-100:]
        item.risk_flags = list(dict.fromkeys(flags))[-100:]
        item.auto_apply_allowed = False
        return item

    def apply_governance_guards(self, allocation: StrategyBudgetAllocation) -> StrategyBudgetAllocation:
        item = StrategyBudgetAllocation.from_dict(allocation)
        reasons = list(dict.fromkeys(item.reason_codes or []))
        flags = list(dict.fromkeys(item.risk_flags or []))
        raw = item.raw_payload if isinstance(item.raw_payload, dict) else {}
        governance = str(raw.get("governance_status") or raw.get("governance_decision") or "").strip().lower()
        tokens = {governance} | {str(x).strip().lower() for x in reasons + flags}
        if tokens & _BLOCKED_GOVERNANCE:
            reasons.append("governance_blocked_budget_zero")
            return replace(item, requested_ratio=0.0, suggested_ratio=0.0, min_floor_ratio=0.0, hard_cap_ratio=0.0, budget_status="blocked", reason_codes=list(dict.fromkeys(reasons))[-100:], risk_flags=flags[-100:], auto_apply_allowed=False)
        item.auto_apply_allowed = False
        return item

    def normalize_allocations(self, allocations: list[StrategyBudgetAllocation]) -> list[StrategyBudgetAllocation]:
        items = [StrategyBudgetAllocation.from_dict(item) for item in allocations or []]
        if not items:
            return []
        for item in items:
            item.auto_apply_allowed = False
            item.suggested_ratio = max(0.0, min(float(item.suggested_ratio or 0.0), float(item.hard_cap_ratio if item.hard_cap_ratio is not None else 1.0)))
            if item.budget_status != "blocked":
                item.suggested_ratio = max(item.suggested_ratio, max(0.0, float(item.min_floor_ratio or 0.0)))
        positives = [item for item in items if item.budget_status != "blocked"]
        if not positives or sum(item.suggested_ratio for item in positives) <= 0:
            return self._fallback_allocations(items)
        self._reduce_to_one(items)
        self._fill_to_one(items)
        for item in items:
            item.suggested_ratio = round(max(0.0, item.suggested_ratio), 6)
            item.auto_apply_allowed = False
        drift = 1.0 - sum(item.suggested_ratio for item in items)
        if abs(drift) > self.normalization_tolerance:
            receiver = self._residual_receiver(items)
            if receiver is not None:
                receiver.suggested_ratio = round(max(0.0, receiver.suggested_ratio + drift), 6)
                receiver.reason_codes = list(dict.fromkeys((receiver.reason_codes or []) + ["strategy_budget_normalization_residual"]))[-100:]
        return [StrategyBudgetAllocation.from_dict(item) for item in items]

    def _reduce_to_one(self, items: list[StrategyBudgetAllocation]) -> None:
        total = sum(item.suggested_ratio for item in items)
        if total <= 1.0:
            return
        reducible = [item for item in items if item.budget_status != "blocked" and item.suggested_ratio > item.min_floor_ratio]
        while total > 1.0 + 1e-9 and reducible:
            excess = total - 1.0
            capacity = sum(item.suggested_ratio - item.min_floor_ratio for item in reducible)
            if capacity <= 0:
                break
            for item in reducible:
                reduction = excess * ((item.suggested_ratio - item.min_floor_ratio) / capacity)
                item.suggested_ratio = max(item.min_floor_ratio, item.suggested_ratio - reduction)
            total = sum(item.suggested_ratio for item in items)
            reducible = [item for item in items if item.budget_status != "blocked" and item.suggested_ratio > item.min_floor_ratio + 1e-9]

    def _fill_to_one(self, items: list[StrategyBudgetAllocation]) -> None:
        total = sum(item.suggested_ratio for item in items)
        if total >= 1.0 - 1e-9:
            return
        preferred = sorted(
            [item for item in items if item.budget_status != "blocked"],
            key=lambda item: 0 if item.budget_status == "baseline" else 1 if item.budget_status == "scale_limited" else 2 if item.budget_status == "test" else 3,
        )
        remaining = 1.0 - total
        for item in preferred:
            cap = item.hard_cap_ratio
            if item.budget_status == "baseline":
                cap = max(cap, 1.0)
            room = max(0.0, cap - item.suggested_ratio)
            add = min(room, remaining)
            item.suggested_ratio += add
            if item.suggested_ratio > item.hard_cap_ratio:
                item.hard_cap_ratio = item.suggested_ratio
            remaining -= add
            if remaining <= 1e-9:
                break

    def _fallback_allocations(self, items: list[StrategyBudgetAllocation]) -> list[StrategyBudgetAllocation]:
        legacy = next((item for item in items if item.strategy_id == "legacy_baseline" or item.strategy_type == "legacy_baseline"), None)
        random = next((item for item in items if item.strategy_id == "random_exploration" or item.strategy_type == "random_exploration"), None)
        if legacy is not None:
            legacy.suggested_ratio = 0.95
            legacy.min_floor_ratio = max(legacy.min_floor_ratio, self.legacy_floor)
            legacy.hard_cap_ratio = max(legacy.hard_cap_ratio, 0.95)
            legacy.budget_status = "baseline"
            legacy.reason_codes = list(dict.fromkeys((legacy.reason_codes or []) + ["fallback_legacy_baseline_budget"]))[-100:]
        if random is not None:
            random.suggested_ratio = 0.05
            random.min_floor_ratio = max(random.min_floor_ratio, self.exploration_floor)
            random.hard_cap_ratio = max(random.hard_cap_ratio, 0.05)
            random.budget_status = "exploration"
            random.reason_codes = list(dict.fromkeys((random.reason_codes or []) + ["fallback_random_exploration_budget"]))[-100:]
        if legacy is None and random is None and items:
            items[0].suggested_ratio = 1.0
            items[0].hard_cap_ratio = 1.0
            items[0].budget_status = "baseline"
            items[0].reason_codes = list(dict.fromkeys((items[0].reason_codes or []) + ["fallback_first_strategy_budget"]))[-100:]
        for item in items:
            if item is not legacy and item is not random:
                item.suggested_ratio = 0.0
            item.auto_apply_allowed = False
        return [StrategyBudgetAllocation.from_dict(item) for item in items]

    def _residual_receiver(self, items: list[StrategyBudgetAllocation]) -> StrategyBudgetAllocation | None:
        for status in ("baseline", "scale_limited", "test", "exploration", "observe"):
            for item in items:
                if item.budget_status == status and item.budget_status != "blocked":
                    return item
        return None

    def _effective_state(self, state: StrategyState) -> str:
        item = StrategyState.from_dict(state)
        return str(item.recommended_state or item.current_state or "shadow").strip().lower()

    def _is_legacy(self, state: StrategyState) -> bool:
        return state.strategy_id == "legacy_baseline" or state.strategy_type == "legacy_baseline"

    def _is_random(self, state: StrategyState) -> bool:
        return state.strategy_id == "random_exploration" or state.strategy_type == "random_exploration"

    def _has_high_sc(self, item: StrategyBudgetAllocation) -> bool:
        flags = {str(flag).strip().lower() for flag in item.risk_flags or []}
        reasons = {str(reason).strip().lower() for reason in item.reason_codes or []}
        return bool((flags | reasons) & _HIGH_SC_FLAGS)

    def _insufficient_evidence(self, item: StrategyBudgetAllocation) -> bool:
        reasons = {str(reason).strip().lower() for reason in item.reason_codes or []}
        raw = item.raw_payload if isinstance(item.raw_payload, dict) else {}
        sample_count = int(raw.get("sample_count") or 0)
        evidence_count = int(raw.get("evidence_count") or 0)
        return item.confidence in {"insufficient", "low"} or bool(reasons & _INSUFFICIENT_REASONS) or (sample_count <= 0 and evidence_count <= 0)

    @property
    def legacy_floor(self) -> float:
        return max(0.40, min(1.0, float(getattr(self.config, "strategy_budget_legacy_min_ratio", 0.40) or 0.40)))

    @property
    def exploration_floor(self) -> float:
        return max(0.05, min(1.0, float(getattr(self.config, "strategy_budget_exploration_min_ratio", 0.05) or 0.05)))

    @property
    def shadow_cap(self) -> float:
        return max(0.0, min(1.0, float(getattr(self.config, "strategy_budget_shadow_max_ratio", 0.02) or 0.02)))

    @property
    def challenger_cap(self) -> float:
        return max(0.0, min(1.0, float(getattr(self.config, "strategy_budget_challenger_max_ratio", 0.20) or 0.20)))

    @property
    def limited_active_cap(self) -> float:
        return max(0.0, min(1.0, float(getattr(self.config, "strategy_budget_limited_active_max_ratio", 0.35) or 0.35)))

    @property
    def high_risk_cap(self) -> float:
        return max(0.0, min(1.0, float(getattr(self.config, "strategy_budget_high_risk_max_ratio", 0.05) or 0.05)))

    @property
    def high_sc_cap(self) -> float:
        return max(0.0, min(1.0, float(getattr(self.config, "strategy_budget_high_sc_max_ratio", 0.05) or 0.05)))

    @property
    def insufficient_evidence_cap(self) -> float:
        return max(0.0, min(1.0, float(getattr(self.config, "strategy_budget_insufficient_evidence_max_ratio", 0.02) or 0.02)))

    @property
    def non_champion_cap(self) -> float:
        return max(0.0, min(1.0, float(getattr(self.config, "strategy_budget_non_champion_max_ratio", 0.35) or 0.35)))

    @property
    def normalization_tolerance(self) -> float:
        return max(0.0, float(getattr(self.config, "strategy_budget_normalization_tolerance", 0.001) or 0.001))
