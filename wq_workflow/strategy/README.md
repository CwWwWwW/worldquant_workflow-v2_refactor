# Phase 6A Strategy Registry / Scoreboard

This package contains the Phase 6A advisory-only Strategy Registry / Scoreboard layer.

It registers strategy profiles for legacy baseline, random exploration, experiment budgeting, ML parent/mutation policies, replay-supported policies, counterfactual-supported policies, governance-safe policies, and manual/unknown fallbacks.

6A only reads evidence and scores strategies. It does **not**:

- run Champion/Challenger promotion,
- allocate or auto-apply strategy budgets,
- take over alpha generation or candidate selection,
- modify reward semantics or CandidatePool ranking,
- change browser/platform automation,
- change Governance hard-decision flags,
- treat counterfactual estimates as actual outcomes.

Counterfactual evidence is always marked as estimated-not-observed and remains advisory. Replay, counterfactual, experiment, governance, and ML evidence are read fail-open; missing sources produce warnings rather than blocking the legacy workflow.

The advisory report is written to `runtime/status/strategy_scoreboard.json` when `StrategyService.refresh_scoreboard()` is called, or when `strategy_scoreboard_auto_refresh=true` during bootstrap. By default auto refresh is disabled.

## Phase 6B: Champion / Challenger Strategy Portfolio

Phase 6B adds an advisory Champion / Challenger Strategy Portfolio layer on top of the Phase 6A Strategy Registry / Scoreboard.

- The default champion is `legacy_baseline`.
- Strategies may be reported as `disabled`, `shadow`, `challenger`, `limited_active`, or `champion`.
- Transitions are recommendations only; every transition has `auto_apply_allowed=false`.
- `limited_active` is still advisory and does not change candidate generation, parent selection, mutation policy, reward, CandidatePool, platform automation, or Governance hard-decision flags.
- Champion replacement is not automatic in this phase; non-baseline strategies can only become future candidates.
- Strategy Budget Allocator is a separate 6C advisory layer and is not applied by the 6B service.
- Existing portfolio/champion/budget/promotion/rollback modules are retained for compatibility. Promotion and rollback tools remain manual and are not called by the 6B service.

Primary advisory status output: `runtime/status/strategy_portfolio_report.json`.

Conservative defaults:

- `enable_strategy_champion_challenger=false`
- `strategy_portfolio_auto_refresh=false`
- `strategy_portfolio_mode=advisory`
- `strategy_allow_auto_champion_promotion=false`
- `strategy_transition_auto_apply=false`
- `enable_strategy_budget_allocator=false`
- `strategy_budget_allocator_auto_apply=false`

## Phase 6C: Strategy Budget Allocator

Phase 6C adds an advisory-only Strategy Budget Allocator on top of the 6A scoreboard and 6B portfolio states.

- Output: `runtime/status/strategy_budget_report.json`.
- All allocations have `auto_apply_allowed=false`.
- `legacy_baseline` keeps a conservative floor of at least `0.40`.
- `random_exploration` keeps a conservative exploration floor of at least `0.05`.
- `disabled`, governance-blocked, and blocked-risk strategies receive zero advisory budget.
- `shadow`, `challenger`, and `limited_active` states are capped as observe/test/scale-limited budgets.
- high-risk, high-SC-risk, and insufficient-evidence strategies are capped conservatively.
- Ratios are normalized for reporting only.

6C does **not** auto-apply budgets, change alpha generation, parent selection, mutation policy, reward semantics, CandidatePool ranking, platform automation, WAIT_RESULT/PARSE_RESULT behavior, SC collection, or Governance hard-decision flags. It does not call promotion or rollback execution paths.

Existing `portfolio.py`, `champion_challenger.py`, `promotion.py`, `rollback.py`, and the legacy `BudgetAllocator` import path remain available for compatibility and are isolated from 6C automatic execution. `StrategyBudgetService.refresh_budget_plan()` is a manual/advisory report generator unless explicitly enabled for advisory auto-refresh; even then it never applies a real budget.

Additional conservative defaults:

- `strategy_budget_mode=advisory`
- `strategy_budget_auto_refresh=false`
- `strategy_budget_auto_apply=false`
- `strategy_budget_allocator_auto_apply=false`
