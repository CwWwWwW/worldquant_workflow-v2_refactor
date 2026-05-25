from __future__ import annotations

from wq_workflow.strategy.budget_allocator import StrategyBudgetAllocator
from wq_workflow.strategy.budget_policy import StrategyBudgetPolicy
from wq_workflow.strategy.portfolio_schema import StrategyState


def _state(strategy_id: str, state: str, **kw):
    return StrategyState(strategy_id=strategy_id, strategy_type=kw.pop("strategy_type", strategy_id), recommended_state=state, current_role=kw.pop("role", "unknown"), **kw)


def test_strategy_budget_policy_floors_caps_and_blocks():
    policy = StrategyBudgetPolicy()
    assert policy.floor_for_strategy(_state("legacy_baseline", "champion", strategy_type="legacy_baseline")) >= 0.40
    assert policy.floor_for_strategy(_state("random_exploration", "shadow", strategy_type="random_exploration")) >= 0.05
    alloc = StrategyBudgetAllocator().build_budget_plan([
        _state("legacy_baseline", "champion", strategy_type="legacy_baseline", confidence="high", risk_level="low"),
        _state("random_exploration", "shadow", strategy_type="random_exploration", confidence="low", risk_level="low"),
        _state("disabled_s", "disabled", risk_level="low"),
        _state("blocked_s", "challenger", risk_level="low", governance_status="blocked"),
        _state("shadow_s", "shadow", confidence="medium", risk_level="low", sample_count=200),
        _state("challenger_s", "challenger", confidence="high", risk_level="low", sample_count=200, evidence_count=10),
        _state("limited_s", "limited_active", confidence="high", risk_level="low", sample_count=600, evidence_count=20),
        _state("high_risk_s", "challenger", confidence="high", risk_level="high", sample_count=200, evidence_count=10),
        _state("high_sc_s", "challenger", confidence="high", risk_level="low", sample_count=200, evidence_count=10, risk_flags=["high_sc_risk"]),
        _state("insufficient_s", "challenger", confidence="insufficient", risk_level="low"),
    ]).allocations
    by_id = {a.strategy_id: a for a in alloc}
    assert by_id["legacy_baseline"].min_floor_ratio >= 0.40
    assert by_id["random_exploration"].min_floor_ratio >= 0.05
    assert by_id["disabled_s"].suggested_ratio == 0
    assert by_id["blocked_s"].suggested_ratio == 0
    assert by_id["shadow_s"].suggested_ratio <= 0.02
    assert by_id["challenger_s"].suggested_ratio <= 0.20
    assert by_id["limited_s"].suggested_ratio <= 0.35
    assert by_id["high_risk_s"].hard_cap_ratio <= 0.05
    assert by_id["high_sc_s"].hard_cap_ratio <= 0.05
    assert by_id["insufficient_s"].hard_cap_ratio <= 0.02
    assert all(a.auto_apply_allowed is False for a in alloc)
