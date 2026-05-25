from __future__ import annotations

import uuid
from typing import Any

from .budget_policy import StrategyBudgetPolicy
from .budget_schema import StrategyBudgetAllocation, StrategyBudgetPlan, utc_now_iso
from .portfolio_schema import StrategyState


class BudgetAllocator:
    def __init__(self, config: Any, logger: Any | None = None) -> None:
        self.config = config
        self.logger = logger

    def allocate(self, strategies: list[dict]) -> dict[str, float]:
        rows = [s for s in strategies or [] if isinstance(s, dict)]
        ids = [str(s.get("strategy_id") or "") for s in rows if s.get("strategy_id")]
        champion = next((s for s in rows if s.get("role") == "champion" and s.get("status", "active") == "active"), None)
        champion_id = str((champion or {}).get("strategy_id") or getattr(self.config, "strategy_default_champion", "legacy_champion") or "legacy_champion")
        out = {sid: 0.0 for sid in ids}
        out.setdefault(champion_id, 0.0)
        if not getattr(self.config, "enable_strategy_portfolio", True):
            out[champion_id] = 1.0
            return self._normalize(out, champion_id)
        if not getattr(self.config, "enable_challenger_live_budget", False):
            out[champion_id] = 1.0
            return self._normalize(out, champion_id)

        challenger_budget = max(0.0, min(1.0, float(getattr(self.config, "strategy_challenger_live_budget", 0.0) or 0.0)))
        baseline_budget = max(0.0, min(1.0, float(getattr(self.config, "strategy_random_baseline_budget", 0.0) or 0.0)))
        if challenger_budget + baseline_budget > 1.0:
            scale = 1.0 / (challenger_budget + baseline_budget)
            challenger_budget *= scale
            baseline_budget *= scale
        safe_challengers = [
            s for s in rows
            if s.get("role") == "challenger"
            and s.get("status", "active") == "active"
            and bool(s.get("safety_pass") or s.get("safety_status") in {"pass", "passed", "safe"})
        ]
        out[champion_id] = max(0.0, 1.0 - challenger_budget - baseline_budget)
        share = challenger_budget / len(safe_challengers) if safe_challengers else 0.0
        for strategy in safe_challengers:
            out[str(strategy.get("strategy_id"))] = share
        if "random_baseline" in out:
            out["random_baseline"] = baseline_budget
        else:
            out["random_baseline"] = baseline_budget
        if not safe_challengers:
            out[champion_id] += challenger_budget
        return self._normalize(out, champion_id)

    def _normalize(self, allocations: dict[str, float], champion_id: str) -> dict[str, float]:
        total = sum(max(0.0, float(v or 0.0)) for v in allocations.values())
        if total <= 0:
            return {**{k: 0.0 for k in allocations}, champion_id: 1.0}
        normalized = {k: max(0.0, float(v or 0.0)) / total for k, v in allocations.items()}
        drift = 1.0 - sum(normalized.values())
        normalized[champion_id] = max(0.0, normalized.get(champion_id, 0.0) + drift)
        return normalized


class StrategyBudgetAllocator:
    def __init__(self, config: Any | None = None, logger: Any | None = None, policy: StrategyBudgetPolicy | None = None) -> None:
        self.config = config
        self.logger = logger
        self.policy = policy or StrategyBudgetPolicy(config=config, logger=logger)

    def build_budget_plan(self, states: list[StrategyState], total_budget_hint: int | None = None) -> StrategyBudgetPlan:
        try:
            plan_id = f"strategy_budget_plan:{uuid.uuid4().hex}"
            normalized_states = self._ensure_core_states([StrategyState.from_dict(item) for item in states or []])
            allocations = [self.build_allocation(state, plan_id, total_budget_hint=total_budget_hint) for state in normalized_states]
            allocations = self.apply_policy(allocations)
            plan = StrategyBudgetPlan(
                plan_id=plan_id,
                generated_at=utc_now_iso(),
                mode=str(getattr(self.config, "strategy_budget_mode", "advisory") or "advisory"),
                total_budget_hint=total_budget_hint,
                allocations=allocations,
                total_suggested_ratio=sum(item.suggested_ratio for item in allocations),
                warnings=[],
                raw_payload={"advisory_only": True, "auto_apply_allowed": False},
            )
            return self.validate_plan(plan)
        except Exception as exc:
            self._warn("strategy budget plan build failed: %s", exc)
            return StrategyBudgetPlan(
                plan_id=f"strategy_budget_plan:failed_open:{uuid.uuid4().hex}",
                generated_at=utc_now_iso(),
                mode="advisory",
                total_budget_hint=total_budget_hint,
                allocations=[],
                total_suggested_ratio=0.0,
                warnings=[f"strategy_budget_allocator_fail_open: {exc}"],
                raw_payload={"advisory_only": True, "fail_open": True},
            )

    def build_allocation(self, state: StrategyState, plan_id: str, total_budget_hint: int | None = None) -> StrategyBudgetAllocation:
        item = StrategyState.from_dict(state)
        effective_state = str(item.recommended_state or item.current_state or "shadow").strip().lower()
        requested = self.policy.requested_ratio_from_state(item)
        floor = self.policy.floor_for_strategy(item)
        cap = max(self.policy.cap_for_state(item), floor)
        suggested = 0.0 if effective_state == "disabled" else min(max(requested, floor), cap)
        if self._is_counterfactual_only_high_risk(item):
            cap = min(cap, float(getattr(self.config, "strategy_budget_high_risk_max_ratio", 0.05) or 0.05))
            suggested = min(suggested, cap)
        allocation = StrategyBudgetAllocation(
            allocation_id=f"strategy_budget_allocation:{uuid.uuid4().hex}",
            plan_id=plan_id,
            strategy_id=item.strategy_id,
            strategy_type=item.strategy_type,
            state=effective_state,
            role=item.current_role,
            score=item.score,
            confidence=item.confidence,
            risk_level=item.risk_level,
            requested_ratio=requested,
            suggested_ratio=suggested,
            min_floor_ratio=floor,
            hard_cap_ratio=cap,
            suggested_slots=self._slots(suggested, total_budget_hint),
            budget_status=self.policy.status_for_state(item),
            reason_codes=list(dict.fromkeys(item.reason_codes or []))[-100:],
            risk_flags=list(dict.fromkeys(item.risk_flags or []))[-100:],
            auto_apply_allowed=False,
            created_at=utc_now_iso(),
            raw_payload={
                "advisory_only": True,
                "auto_apply_allowed": False,
                "governance_status": item.governance_status,
                "sample_count": item.sample_count,
                "evidence_count": item.evidence_count,
                "strategy_state": item.to_dict(),
            },
        )
        return StrategyBudgetAllocation.from_dict(allocation)

    def apply_policy(self, allocations: list[StrategyBudgetAllocation]) -> list[StrategyBudgetAllocation]:
        guarded: list[StrategyBudgetAllocation] = []
        for allocation in allocations or []:
            item = self.policy.apply_governance_guards(allocation)
            item = self.policy.apply_risk_guards(item)
            guarded.append(item)
        return self.normalize_allocations(guarded)

    def normalize_allocations(self, allocations: list[StrategyBudgetAllocation]) -> list[StrategyBudgetAllocation]:
        return self.policy.normalize_allocations(allocations)

    def validate_plan(self, plan: StrategyBudgetPlan) -> StrategyBudgetPlan:
        item = StrategyBudgetPlan.from_dict(plan)
        total_hint = item.total_budget_hint
        warnings = list(item.warnings or [])
        total = sum(max(0.0, float(allocation.suggested_ratio or 0.0)) for allocation in item.allocations)
        tolerance = float(getattr(self.config, "strategy_budget_normalization_tolerance", 0.001) or 0.001)
        if item.allocations and abs(total - 1.0) > tolerance:
            warnings.append("strategy_budget_total_ratio_outside_tolerance")
        if item.allocations and any(allocation.budget_status == "blocked" for allocation in item.allocations) and all(allocation.suggested_ratio <= 0 for allocation in item.allocations):
            warnings.append("strategy_budget_all_blocked_fallback")
        for allocation in item.allocations:
            allocation.auto_apply_allowed = False
            allocation.suggested_slots = self._slots(allocation.suggested_ratio, total_hint)
        item.total_suggested_ratio = round(sum(allocation.suggested_ratio for allocation in item.allocations), 6)
        item.warnings = list(dict.fromkeys(warnings))[-100:]
        item.raw_payload = {**(item.raw_payload if isinstance(item.raw_payload, dict) else {}), "advisory_only": True, "auto_apply_allowed": False}
        return StrategyBudgetPlan.from_dict(item)

    def _ensure_core_states(self, states: list[StrategyState]) -> list[StrategyState]:
        out = [StrategyState.from_dict(item) for item in states or []]
        default_champion = str(getattr(self.config, "strategy_default_champion", "legacy_baseline") or "legacy_baseline")
        if not any(item.strategy_id == default_champion or item.strategy_type == "legacy_baseline" for item in out):
            out.insert(
                0,
                StrategyState(
                    strategy_id=default_champion,
                    strategy_type="legacy_baseline",
                    current_state="champion",
                    recommended_state="champion",
                    current_role="baseline",
                    confidence="medium",
                    risk_level="low",
                    score=0.5,
                    reason_codes=["default_champion_legacy_baseline", "budget_allocator_synthesized_baseline"],
                    raw_payload={"advisory_only": True, "synthesized_by": "strategy_budget_allocator"},
                ),
            )
        if not any(item.strategy_id == "random_exploration" or item.strategy_type == "random_exploration" for item in out):
            out.append(
                StrategyState(
                    strategy_id="random_exploration",
                    strategy_type="random_exploration",
                    current_state="shadow",
                    recommended_state="shadow",
                    current_role="observer",
                    confidence="low",
                    risk_level="low",
                    score=0.0,
                    reason_codes=["budget_allocator_synthesized_exploration"],
                    raw_payload={"advisory_only": True, "synthesized_by": "strategy_budget_allocator"},
                )
            )
        return out

    def _slots(self, ratio: float, total_budget_hint: int | None) -> int | None:
        if total_budget_hint is None:
            return None
        try:
            return max(0, int(round(max(0.0, float(ratio or 0.0)) * max(0, int(total_budget_hint)))))
        except Exception:
            return None

    def _is_counterfactual_only_high_risk(self, state: StrategyState) -> bool:
        text = f"{state.strategy_id} {state.strategy_type} {' '.join(state.reason_codes or [])} {' '.join(state.risk_flags or [])}".lower()
        return "counterfactual" in text and (state.risk_level == "high" or "high_risk" in text)

    def _warn(self, message: str, exc: Exception) -> None:
        try:
            if self.logger is not None:
                self.logger.warning(message, exc)
        except Exception:
            pass
